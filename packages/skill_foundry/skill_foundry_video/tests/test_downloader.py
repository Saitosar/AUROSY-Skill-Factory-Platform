"""Tests for YouTube video downloader."""

import pytest
from skill_foundry_video.downloader import (
    _extract_youtube_video_id,
    VideoDownloader,
    VideoMetadata,
)


class TestYouTubeIdExtraction:
    def test_standard_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert _extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert _extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        assert _extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_url_with_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"
        assert _extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        assert _extract_youtube_video_id("https://example.com/video") is None
        assert _extract_youtube_video_id("not a url") is None


class TestVideoMetadata:
    def test_to_dict(self, tmp_path):
        metadata = VideoMetadata(
            video_id="test123",
            title="Test Video",
            duration_sec=10.5,
            fps=30.0,
            width=1280,
            height=720,
            file_path=tmp_path / "test.mp4",
            file_size_bytes=1024,
            sha256="abc123",
            source_url="https://youtube.com/watch?v=test123",
        )

        d = metadata.to_dict()

        assert d["video_id"] == "test123"
        assert d["duration_sec"] == 10.5
        assert d["fps"] == 30.0
        assert "file_path" in d


class TestVideoDownloader:
    def test_init_creates_directory(self, tmp_path):
        output_dir = tmp_path / "videos"
        downloader = VideoDownloader(output_dir=output_dir)
        assert output_dir.exists()

    def test_invalid_url_raises(self, tmp_path):
        downloader = VideoDownloader(output_dir=tmp_path)
        with pytest.raises(ValueError, match="Invalid YouTube URL"):
            downloader.download("https://example.com/not-youtube")
