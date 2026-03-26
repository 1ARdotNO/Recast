"""Apple Podcasts RSS compliance checks."""

from __future__ import annotations

import structlog

from recast.models.show import ShowConfig

logger = structlog.get_logger()


def validate_apple_compliance(config: ShowConfig) -> list[str]:
    """Check Apple Podcasts specific requirements.

    Returns list of issues found.
    """
    issues = []

    # Required: show title
    if not config.name or config.name == "Untitled Show":
        issues.append("Apple Podcasts requires a show title")

    # Required: show description
    if not config.description:
        issues.append("Apple Podcasts requires a show description")

    # Required: artwork (1400x1400 to 3000x3000 JPEG or PNG)
    if not config.cover_image:
        issues.append(
            "Apple Podcasts requires artwork "
            "(minimum 1400x1400px, JPEG or PNG)"
        )
    else:
        cover_path = config.resolve_path(config.cover_image)
        if not cover_path.exists():
            issues.append(f"Cover image file not found: {cover_path}")
        elif cover_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            issues.append(
                "Apple Podcasts requires JPEG or PNG artwork "
                f"(found {cover_path.suffix})"
            )

    # Required: author
    if not config.author:
        issues.append("Apple Podcasts requires an author name")

    # Required: language
    if not config.language:
        issues.append("Apple Podcasts requires a language code")

    # Required: category
    if not config.itunes_category:
        issues.append("Apple Podcasts requires at least one category")

    # Required: explicit tag
    # (handled automatically in feed generation)

    # feed_base_url needed for enclosure URLs
    if not config.feed_base_url:
        issues.append(
            "feed_base_url must be set for Apple Podcasts — "
            "episode audio must be publicly accessible via HTTPS"
        )

    if issues:
        logger.warning("apple.compliance_issues", n_issues=len(issues))
    else:
        logger.info("apple.compliant")

    return issues
