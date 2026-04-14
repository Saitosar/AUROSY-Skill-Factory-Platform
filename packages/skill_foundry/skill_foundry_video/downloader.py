"""YouTube video downloader using yt-dlp."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_VIDEO_DURATION_SEC = 120
DEFAULT_MAX_RESOLUTION = 720


@dataclass
class VideoMetadata:
    """Metadata extracted from downloaded video."""

    video_id: str
    title: str
    duration_sec: float
    fps: float
    width: int
    height: int
    file_path: Path
    file_size_bytes: int
    sha256: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "duration_sec": self.duration_sec,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "file_path": str(self.file_path),
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "source_url": self.source_url,
        }


def _extract_youtube_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_video_info_ffprobe(path: Path) -> dict[str, Any]:
    """Get video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        logger.warning("ffprobe failed: %s", e)
        return {}


class VideoDownloader:
    """Download YouTube videos with configurable options."""

    def __init__(
        self,
        output_dir: Path,
        max_duration_sec: float = MAX_VIDEO_DURATION_SEC,
        max_resolution: int = DEFAULT_MAX_RESOLUTION,
    ):
        self.output_dir = Path(output_dir)
        self.max_duration_sec = max_duration_sec
        self.max_resolution = max_resolution
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        *,
        start_sec: float | None = None,
        end_sec: float | None = None,
        filename: str | None = None,
    ) -> VideoMetadata:
        """Download video from YouTube URL.

        Args:
            url: YouTube video URL
            start_sec: Optional start time for trimming
            end_sec: Optional end time for trimming
            filename: Optional output filename (without extension)

        Returns:
            VideoMetadata with download result

        Raises:
            ValueError: If URL is invalid or video too long
            RuntimeError: If download fails
        """
        video_id = _extract_youtube_video_id(url)
        if not video_id:
            raise ValueError(f"Invalid YouTube URL: {url}")

        info = self._fetch_video_info(url)
        duration = float(info.get("duration", 0))

        if duration > self.max_duration_sec:
            raise ValueError(
                f"Video duration ({duration:.1f}s) exceeds maximum "
                f"({self.max_duration_sec}s). Please use start_sec/end_sec to trim."
            )

        out_filename = filename or f"{video_id}"
        out_path = self.output_dir / f"{out_filename}.mp4"

        self._download_video(url, out_path, start_sec, end_sec)

        probe_info = _get_video_info_ffprobe(out_path)
        video_stream = next(
            (s for s in probe_info.get("streams", []) if s.get("codec_type") == "video"),
            {},
        )

        fps_str = video_stream.get("r_frame_rate", "30/1")
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den)
            else:
                fps = float(fps_str)
        except (ValueError, ZeroDivisionError):
            fps = 30.0

        actual_duration = float(probe_info.get("format", {}).get("duration", duration))
        if start_sec is not None and end_sec is not None:
            actual_duration = min(actual_duration, end_sec - start_sec)

        return VideoMetadata(
            video_id=video_id,
            title=info.get("title", "Unknown"),
            duration_sec=actual_duration,
            fps=fps,
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            file_path=out_path,
            file_size_bytes=out_path.stat().st_size,
            sha256=_sha256_file(out_path),
            source_url=url,
        )

    def _fetch_video_info(self, url: str) -> dict[str, Any]:
        """Fetch video metadata without downloading."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            url,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to fetch video info: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from yt-dlp: {e}") from e

    def _download_video(
        self,
        url: str,
        output_path: Path,
        start_sec: float | None,
        end_sec: float | None,
    ) -> None:
        """Download and optionally trim video."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "video.mp4"

            format_spec = f"bestvideo[height<={self.max_resolution}]+bestaudio/best[height<={self.max_resolution}]"
            cmd = [
                "yt-dlp",
                "-f", format_spec,
                "--merge-output-format", "mp4",
                "-o", str(tmp_path),
                url,
            ]

            logger.info("Downloading video: %s", url)
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"yt-dlp download failed: {e.stderr}") from e

            if start_sec is not None or end_sec is not None:
                self._trim_video(tmp_path, output_path, start_sec, end_sec)
            else:
                tmp_path.rename(output_path)

    def _trim_video(
        self,
        input_path: Path,
        output_path: Path,
        start_sec: float | None,
        end_sec: float | None,
    ) -> None:
        """Trim video using ffmpeg."""
        cmd = ["ffmpeg", "-y", "-i", str(input_path)]

        if start_sec is not None:
            cmd.extend(["-ss", str(start_sec)])
        if end_sec is not None:
            if start_sec is not None:
                cmd.extend(["-t", str(end_sec - start_sec)])
            else:
                cmd.extend(["-t", str(end_sec)])

        cmd.extend(["-c", "copy", str(output_path)])

        logger.info("Trimming video: start=%s, end=%s", start_sec, end_sec)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg trim failed: {e.stderr}") from e


def download_youtube_video(
    url: str,
    output_dir: Path | str,
    *,
    start_sec: float | None = None,
    end_sec: float | None = None,
    max_duration_sec: float = MAX_VIDEO_DURATION_SEC,
    max_resolution: int = DEFAULT_MAX_RESOLUTION,
) -> VideoMetadata:
    """Convenience function to download a YouTube video.

    Args:
        url: YouTube video URL
        output_dir: Directory to save the video
        start_sec: Optional start time for trimming
        end_sec: Optional end time for trimming
        max_duration_sec: Maximum allowed video duration
        max_resolution: Maximum video resolution (height)

    Returns:
        VideoMetadata with download result
    """
    downloader = VideoDownloader(
        output_dir=Path(output_dir),
        max_duration_sec=max_duration_sec,
        max_resolution=max_resolution,
    )
    return downloader.download(url, start_sec=start_sec, end_sec=end_sec)


def main() -> None:
    """CLI entry point for video download."""
    import argparse

    parser = argparse.ArgumentParser(description="Download YouTube video for motion extraction")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."), help="Output directory")
    parser.add_argument("--start", type=float, help="Start time in seconds")
    parser.add_argument("--end", type=float, help="End time in seconds")
    parser.add_argument("--max-duration", type=float, default=MAX_VIDEO_DURATION_SEC, help="Max duration")
    parser.add_argument("--max-resolution", type=int, default=DEFAULT_MAX_RESOLUTION, help="Max resolution")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    try:
        metadata = download_youtube_video(
            args.url,
            args.output_dir,
            start_sec=args.start,
            end_sec=args.end,
            max_duration_sec=args.max_duration,
            max_resolution=args.max_resolution,
        )
        print(json.dumps(metadata.to_dict(), indent=2))
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
