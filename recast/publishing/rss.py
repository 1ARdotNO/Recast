"""RSS feed generation for Spotify + Apple Podcasts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog
from feedgen.feed import FeedGenerator

from recast.models.show import ShowConfig
from recast.models.episode import Episode

logger = structlog.get_logger()


def _validate_feed(config: ShowConfig) -> list[str]:
    """Validate feed requirements. Returns list of warnings."""
    warnings = []

    if not config.feed_base_url:
        warnings.append("feed_base_url is not set — episode URLs will be invalid")

    if config.cover_image:
        cover_path = config.resolve_path(config.cover_image)
        if cover_path.exists():
            try:
                # Just check file size as a rough proxy for image dimensions
                size = cover_path.stat().st_size
                if size < 50000:  # Very rough — 50KB min for a 1400x1400 image
                    warnings.append(
                        "Cover image may be too small. "
                        "Apple Podcasts requires minimum 1400x1400 pixels."
                    )
            except Exception:
                pass
        else:
            warnings.append(f"Cover image not found: {config.cover_image}")
    else:
        warnings.append(
            "No cover_image set. "
            "Apple Podcasts and Spotify require podcast artwork."
        )

    if not config.name or config.name == "Untitled Show":
        warnings.append("Show name should be set for podcast directories")

    return warnings


def generate_feed(
    config: ShowConfig,
    episodes: list[Episode],
    output_path: Path | None = None,
) -> tuple[str, list[str]]:
    """Generate RSS 2.0 + iTunes namespace feed.

    Returns (feed_xml_string, warnings).
    """
    warnings = _validate_feed(config)

    fg = FeedGenerator()
    fg.load_extension("podcast")

    # Channel metadata
    fg.title(config.name)
    fg.description(config.description or config.name)
    fg.link(href=config.feed_base_url or "https://example.com", rel="alternate")
    fg.language(config.language)
    fg.generator("Recast")

    # iTunes namespace
    fg.podcast.itunes_author(config.author or config.name)
    fg.podcast.itunes_summary(config.description or config.name)
    fg.podcast.itunes_explicit("yes" if config.itunes_explicit else "no")

    if config.itunes_category:
        fg.podcast.itunes_category(config.itunes_category)

    if config.cover_image:
        cover_url = f"{config.feed_base_url}/{config.cover_image}"
        fg.podcast.itunes_image(cover_url)
        fg.image(url=cover_url, title=config.name)

    # Episodes (most recent first)
    for ep in sorted(episodes, key=lambda e: e.published_at or "", reverse=True):
        fe = fg.add_entry()
        fe.id(ep.job_id)
        fe.title(ep.title or f"Episode {ep.job_id[:8]}")
        fe.description(ep.description or "")

        # Audio enclosure
        filename = Path(ep.output_path).name if ep.output_path else f"{ep.job_id}.mp3"
        audio_url = f"{config.feed_base_url}/{filename}"
        file_size = 0
        if ep.output_path and Path(ep.output_path).exists():
            file_size = Path(ep.output_path).stat().st_size
        fe.enclosure(audio_url, str(file_size), "audio/mpeg")

        # iTunes per-episode
        fe.podcast.itunes_duration(int(ep.duration_s))
        fe.podcast.itunes_summary(ep.description or "")

        if ep.published_at:
            fe.published(ep.published_at)
        else:
            fe.published(datetime.now(timezone.utc).isoformat())

        # Podlove Simple Chapters (psc namespace)
        if ep.chapters:
            # Chapters as content:encoded for compatibility
            chapters_html = "<h3>Chapters</h3><ul>"
            for ch in ep.chapters:
                mins = int(ch.start_time // 60)
                secs = int(ch.start_time % 60)
                chapters_html += f"<li>{mins:02d}:{secs:02d} - {ch.title}</li>"
            chapters_html += "</ul>"
            fe.content(chapters_html, type="html")

    feed_xml = fg.rss_str(pretty=True).decode("utf-8")

    # Write to file
    if output_path is None:
        output_path = config.resolve_path(config.feed_file)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(feed_xml, encoding="utf-8")

    logger.info(
        "rss.generated",
        path=str(output_path),
        n_episodes=len(episodes),
        n_warnings=len(warnings),
    )

    return feed_xml, warnings
