"""Stage 5 — Reconcile: Merge pyannote + LLM cut lists into final CutList."""

from __future__ import annotations

from pathlib import Path

import structlog

from recast.models.cut import CutList, CutDecision, CutSource, Segment, SegmentType

logger = structlog.get_logger()


def _segments_to_remove_intervals(
    segments: list[Segment],
) -> list[tuple[float, float]]:
    """Extract non-speech (music) intervals from segment list."""
    return [
        (s.start, s.end) for s in segments if s.type == SegmentType.MUSIC
    ]


def _llm_cuts_to_intervals(
    llm_cuts: list[dict],
) -> list[tuple[float, float, str, float]]:
    """Extract (start, end, reason, confidence) from LLM cuts."""
    return [
        (c["start"], c["end"], c.get("reason", ""), c.get("confidence", 1.0))
        for c in llm_cuts
    ]


def _merge_intervals(
    intervals: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Merge overlapping intervals."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_ivs[0]]
    for start, end in sorted_ivs[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _apply_padding(
    intervals: list[tuple[float, float]],
    pad_s: float,
    total_duration: float,
) -> list[tuple[float, float]]:
    """Add padding around cut boundaries."""
    padded = []
    for start, end in intervals:
        new_start = max(0.0, start - pad_s)
        new_end = min(total_duration, end + pad_s)
        padded.append((new_start, new_end))
    return _merge_intervals(padded)


def reconcile(
    segments: list[Segment],
    llm_cuts: list[dict],
    output_dir: Path,
    total_duration: float,
    cut_pad_ms: int = 300,
    min_keep_duration_s: float = 2.0,
) -> CutList:
    """Merge pyannote segments and LLM cuts into a unified CutList.

    Union rule: a segment is removed if flagged by EITHER source.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "cutlist_final.json"

    logger.info("reconcile.start", total_duration=total_duration)

    pad_s = cut_pad_ms / 1000.0

    # Collect all remove intervals with their source
    pyannote_removes = _segments_to_remove_intervals(segments)
    llm_removes = [(c[0], c[1]) for c in _llm_cuts_to_intervals(llm_cuts)]

    # Build source tracking
    source_map: dict[tuple[float, float], CutSource] = {}
    reason_map: dict[tuple[float, float], str] = {}
    confidence_map: dict[tuple[float, float], float] = {}

    for start, end in pyannote_removes:
        source_map[(start, end)] = CutSource.PYANNOTE
        reason_map[(start, end)] = "music/non-speech"
        confidence_map[(start, end)] = 1.0

    for cut_info in _llm_cuts_to_intervals(llm_cuts):
        start, end, reason, confidence = cut_info
        key = (start, end)
        if key in source_map:
            source_map[key] = CutSource.BOTH
        else:
            source_map[key] = CutSource.LLM
        reason_map[key] = reason
        confidence_map[key] = confidence

    # Union of all remove intervals
    all_removes = list(set(pyannote_removes + llm_removes))
    all_removes = _apply_padding(all_removes, pad_s, total_duration)

    # Invert: compute keep intervals
    keep_intervals: list[tuple[float, float]] = []
    prev_end = 0.0
    for rm_start, rm_end in sorted(all_removes):
        if rm_start > prev_end:
            keep_intervals.append((prev_end, rm_start))
        prev_end = max(prev_end, rm_end)
    if prev_end < total_duration:
        keep_intervals.append((prev_end, total_duration))

    # Filter out keep segments shorter than min_keep_duration_s
    keep_intervals = [
        (s, e) for s, e in keep_intervals
        if (e - s) >= min_keep_duration_s
    ]

    # Build final CutList with both keep and remove decisions
    decisions: list[CutDecision] = []

    # Add all intervals sorted by time
    all_intervals: list[tuple[float, float, bool]] = []
    for s, e in keep_intervals:
        all_intervals.append((s, e, True))
    for s, e in all_removes:
        all_intervals.append((s, e, False))
    all_intervals.sort(key=lambda x: x[0])

    for start, end, keep in all_intervals:
        key = (start, end)
        if keep:
            decisions.append(CutDecision(
                start=start, end=end, keep=True,
                reason="speech", source=CutSource.PYANNOTE, confidence=1.0,
            ))
        else:
            # Find best matching source info
            source = CutSource.PYANNOTE
            reason = "music/non-speech"
            confidence = 1.0
            for orig_key, orig_source in source_map.items():
                if (abs(orig_key[0] - start) < pad_s + 0.01 and
                        abs(orig_key[1] - end) < pad_s + 0.01):
                    source = orig_source
                    reason = reason_map.get(orig_key, reason)
                    confidence = confidence_map.get(orig_key, confidence)
                    break
            decisions.append(CutDecision(
                start=start, end=end, keep=False,
                reason=reason, source=source, confidence=confidence,
            ))

    cutlist = CutList(decisions=decisions, total_duration=total_duration)
    cutlist.save(output_path)

    logger.info(
        "reconcile.done",
        n_keep=len(cutlist.keep_segments),
        n_remove=len(cutlist.remove_segments),
        kept_duration=cutlist.kept_duration,
    )

    return cutlist
