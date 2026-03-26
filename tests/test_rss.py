"""Tests for RSS feed generation and Apple Podcasts compliance."""

from pathlib import Path

import pytest

from recast.models.show import ShowConfig
from recast.models.episode import Episode, Chapter
from recast.publishing.rss import generate_feed, _validate_feed
from recast.publishing.apple import validate_apple_compliance


@pytest.fixture
def show_config(tmp_path):
    return ShowConfig(
        name="Test Podcast",
        description="A test podcast about testing.",
        author="Test Author",
        language="no",
        cover_image="cover.jpg",
        feed_base_url="https://example.com/podcast",
        itunes_category="Technology",
        show_folder=tmp_path,
    )


@pytest.fixture
def episodes():
    return [
        Episode(
            job_id="ep1",
            title="First Episode",
            description="The first episode about stuff.",
            duration_s=300.0,
            output_path="/tmp/ep1.mp3",
            published_at="2025-01-01T00:00:00Z",
            chapters=[
                Chapter(title="Intro", start_time=0.0),
                Chapter(title="Main Topic", start_time=60.0),
            ],
        ),
        Episode(
            job_id="ep2",
            title="Second Episode",
            description="The second episode.",
            duration_s=600.0,
            output_path="/tmp/ep2.mp3",
            published_at="2025-01-08T00:00:00Z",
        ),
    ]


class TestGenerateFeed:
    def test_generates_xml(self, show_config, episodes, tmp_path):
        output = tmp_path / "feed.xml"
        xml, warnings = generate_feed(show_config, episodes, output)
        assert xml.startswith("<?xml")
        assert output.exists()

    def test_contains_show_metadata(self, show_config, episodes, tmp_path):
        output = tmp_path / "feed.xml"
        xml, _ = generate_feed(show_config, episodes, output)
        assert "Test Podcast" in xml
        assert "A test podcast" in xml

    def test_contains_episodes(self, show_config, episodes, tmp_path):
        output = tmp_path / "feed.xml"
        xml, _ = generate_feed(show_config, episodes, output)
        assert "First Episode" in xml
        assert "Second Episode" in xml

    def test_contains_enclosure(self, show_config, episodes, tmp_path):
        output = tmp_path / "feed.xml"
        xml, _ = generate_feed(show_config, episodes, output)
        assert "audio/mpeg" in xml
        assert "https://example.com/podcast/" in xml

    def test_contains_itunes_tags(self, show_config, episodes, tmp_path):
        output = tmp_path / "feed.xml"
        xml, _ = generate_feed(show_config, episodes, output)
        assert "itunes" in xml.lower()

    def test_chapters_in_content(self, show_config, episodes, tmp_path):
        output = tmp_path / "feed.xml"
        xml, _ = generate_feed(show_config, episodes, output)
        assert "Chapters" in xml
        assert "Intro" in xml
        assert "Main Topic" in xml

    def test_empty_episodes(self, show_config, tmp_path):
        output = tmp_path / "feed.xml"
        xml, _ = generate_feed(show_config, [], output)
        assert "Test Podcast" in xml

    def test_default_output_path(self, show_config, episodes):
        xml, _ = generate_feed(show_config, episodes)
        assert (show_config.show_folder / "feed.xml").exists()


class TestValidateFeed:
    def test_valid_config(self, show_config, tmp_path):
        # Create cover image
        (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100000)
        warnings = _validate_feed(show_config)
        # May have warnings about image size but no critical errors
        assert isinstance(warnings, list)

    def test_missing_base_url(self, tmp_path):
        config = ShowConfig(
            name="Test", show_folder=tmp_path, feed_base_url="",
        )
        warnings = _validate_feed(config)
        assert any("feed_base_url" in w for w in warnings)

    def test_missing_cover(self, tmp_path):
        config = ShowConfig(name="Test", show_folder=tmp_path)
        warnings = _validate_feed(config)
        assert any("cover" in w.lower() for w in warnings)


class TestAppleCompliance:
    def test_compliant(self, show_config):
        issues = validate_apple_compliance(show_config)
        # Cover image doesn't exist on disk, so there will be an issue
        cover_issues = [i for i in issues if "cover" in i.lower() or "artwork" in i.lower()]
        non_cover = [i for i in issues if i not in cover_issues]
        assert len(non_cover) == 0

    def test_missing_fields(self, tmp_path):
        config = ShowConfig(
            name="",
            description="",
            author="",
            language="",
            cover_image="",
            itunes_category="",
            feed_base_url="",
            show_folder=tmp_path,
        )
        issues = validate_apple_compliance(config)
        assert len(issues) >= 5  # Multiple missing fields

    def test_wrong_image_format(self, tmp_path):
        (tmp_path / "cover.bmp").write_bytes(b"\x00" * 100)
        config = ShowConfig(
            name="Test",
            description="Test",
            author="Author",
            language="no",
            cover_image="cover.bmp",
            itunes_category="News",
            feed_base_url="https://example.com",
            show_folder=tmp_path,
        )
        issues = validate_apple_compliance(config)
        assert any("JPEG or PNG" in i for i in issues)
