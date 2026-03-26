"""Pipeline runner — orchestrates stages with resume support."""

from __future__ import annotations

import json
import time
from typing import Callable

import structlog

from recast.models.job import Job, PIPELINE_STAGES
from recast.models.show import ShowConfig
from recast.models.cut import CutList, Segment
from recast.models.episode import Episode
from recast.queue import JobQueue

logger = structlog.get_logger()

ProgressCallback = Callable[[str, int, int], None]


class PipelineRunner:
    def __init__(
        self,
        show_config: ShowConfig,
        queue: JobQueue,
        hf_token: str = "",
        progress_callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ):
        self.config = show_config
        self.queue = queue
        self.hf_token = hf_token
        self.progress_callback = progress_callback
        self.dry_run = dry_run

    def _report_progress(self, stage: str, stage_idx: int, total: int) -> None:
        if self.progress_callback:
            self.progress_callback(stage, stage_idx, total)

    def _stage_completed(self, job: Job, stage: str) -> bool:
        """Check if a stage has already completed (for resume)."""
        job_dir = self.config.job_dir(job.id)
        stage_outputs = {
            "normalize": "audio_normalized.wav",
            "segment": "segments_pyannote.json",
            "transcribe": "transcript.json",
            "llm_pass": "cuts_llm.json",
            "reconcile": "cutlist_final.json",
            "render": f"episode_audio.{self.config.audio_format}",
            "metadata": "episode_metadata.json",
        }
        output_file = stage_outputs.get(stage)
        if output_file and (job_dir / output_file).exists():
            return True
        return False

    def _retry_with_backoff(self, func, max_retries: int = 3, *args, **kwargs):
        """Retry function with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(
                    "pipeline.retry",
                    attempt=attempt + 1,
                    wait_s=wait,
                    error=str(e),
                )
                time.sleep(wait)

    def run(self, job: Job) -> Episode | None:
        """Run the full pipeline for a job.

        Returns Episode on success, None on failure.
        """
        job_dir = self.config.job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)

        total_stages = len(PIPELINE_STAGES)

        try:
            # Stage 1: Normalize
            stage_idx = 1
            stage_name = "normalize"
            if not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.normalize import normalize
                wav_path, duration = self._retry_with_backoff(
                    normalize, 3, str(job.input_path), job_dir,
                )
                job.duration_s = duration
                self.queue.update_job(job)
            else:
                wav_path = job_dir / "audio_normalized.wav"
                from recast.pipeline.stages.normalize import get_audio_duration
                job.duration_s = get_audio_duration(str(wav_path))
                logger.info("pipeline.resume", stage=stage_name)

            # Stage 2: Segment
            stage_idx = 2
            stage_name = "segment"
            if not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.segment import segment
                segments = self._retry_with_backoff(
                    segment, 3, wav_path, job_dir,
                    min_speech_gap_s=self.config.min_speech_gap_s,
                    hf_token=self.hf_token,
                )
            else:
                segments_data = json.loads(
                    (job_dir / "segments_pyannote.json").read_text()
                )
                segments = [Segment.from_dict(s) for s in segments_data]
                logger.info("pipeline.resume", stage=stage_name)

            # Stage 3: Transcribe
            stage_idx = 3
            stage_name = "transcribe"
            if not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.transcribe import transcribe
                transcript = self._retry_with_backoff(
                    transcribe, 3, wav_path, job_dir,
                    speech_segments=segments,
                    model_name=self.config.whisper_model,
                    language=self.config.whisper_language,
                )
            else:
                transcript = json.loads(
                    (job_dir / "transcript.json").read_text()
                )
                logger.info("pipeline.resume", stage=stage_name)

            # Stage 4: LLM Pass
            stage_idx = 4
            stage_name = "llm_pass"
            if not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.llm_pass import llm_pass
                llm_cuts = self._retry_with_backoff(
                    llm_pass, 3, transcript, job_dir,
                    ollama_model=self.config.ollama_model,
                    ollama_base_url=self.config.ollama_base_url,
                    confidence_threshold=self.config.llm_confidence_threshold,
                    prompt_template_path=self.config.llm_prompt_template,
                )
            else:
                llm_cuts = json.loads(
                    (job_dir / "cuts_llm.json").read_text()
                )
                logger.info("pipeline.resume", stage=stage_name)

            # Stage 5: Reconcile
            stage_idx = 5
            stage_name = "reconcile"
            # Check for user override
            user_cutlist_path = job_dir / "cutlist_user.json"
            if user_cutlist_path.exists():
                cutlist = CutList.load(user_cutlist_path)
                logger.info("pipeline.user_cutlist", path=str(user_cutlist_path))
            elif not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.reconcile import reconcile
                cutlist = reconcile(
                    segments, llm_cuts, job_dir,
                    total_duration=job.duration_s or 0.0,
                    cut_pad_ms=self.config.cut_pad_ms,
                    min_keep_duration_s=self.config.min_keep_duration_s,
                )
            else:
                cutlist = CutList.load(job_dir / "cutlist_final.json")
                logger.info("pipeline.resume", stage=stage_name)

            # Review mode: pause here for human approval
            if self.config.review_mode:
                job.set_review()
                self.queue.update_job(job)
                logger.info("pipeline.review_mode", job_id=job.id)
                return None

            if self.dry_run:
                logger.info("pipeline.dry_run_stop", job_id=job.id)
                job.complete()
                self.queue.update_job(job)
                return None

            # Stage 6: Render
            stage_idx = 6
            stage_name = "render"
            if not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.render import render
                episode_path = self._retry_with_backoff(
                    render, 3, wav_path, cutlist, job_dir,
                    join_mode=self.config.join_mode,
                    crossfade_duration_ms=self.config.crossfade_duration_ms,
                    silence_duration_ms=self.config.silence_duration_ms,
                    audio_format=self.config.audio_format,
                    audio_bitrate=self.config.audio_bitrate,
                )
            else:
                episode_path = job_dir / f"episode_audio.{self.config.audio_format}"
                logger.info("pipeline.resume", stage=stage_name)

            # Stage 7: Metadata
            stage_idx = 7
            stage_name = "metadata"
            if not self._stage_completed(job, stage_name):
                self._report_progress(stage_name, stage_idx, total_stages)
                job.advance_stage(stage_name)
                self.queue.update_job(job)

                from recast.pipeline.stages.metadata import metadata
                episode = self._retry_with_backoff(
                    metadata, 3, transcript, job_dir,
                    episode_audio_path=episode_path,
                    duration_s=cutlist.kept_duration,
                    job_id=job.id,
                    ollama_model=self.config.ollama_model,
                    ollama_base_url=self.config.ollama_base_url,
                )
            else:
                episode = Episode.load(job_dir / "episode_metadata.json")
                logger.info("pipeline.resume", stage=stage_name)

            # Copy final episode to output folder
            output_dir = self.config.output_path
            output_dir.mkdir(parents=True, exist_ok=True)
            final_path = output_dir / episode_path.name
            if episode_path != final_path:
                import shutil
                shutil.copy2(episode_path, final_path)
                episode.output_path = str(final_path)

            # Stage 8: Publish (handled separately)
            stage_idx = 8
            stage_name = "publish"
            self._report_progress(stage_name, stage_idx, total_stages)
            job.advance_stage(stage_name)

            # Store episode in DB
            try:
                self.queue.create_episode(episode)
            except Exception:
                self.queue.update_episode(episode)

            job.complete()
            self.queue.update_job(job)

            logger.info("pipeline.complete", job_id=job.id, title=episode.title)
            return episode

        except Exception as e:
            logger.error("pipeline.error", job_id=job.id, error=str(e))
            job.fail(str(e))
            self.queue.update_job(job)
            return None
