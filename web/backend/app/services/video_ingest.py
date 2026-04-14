"""Video ingestion service for YouTube video processing."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class VideoIngestResult:
    """Result of video ingestion."""

    video_id: str
    artifact_path: str
    duration_sec: float
    fps: float
    width: int
    height: int
    title: str
    source_url: str


class VideoIngestError(Exception):
    """Error during video ingestion."""

    pass


def _user_videos_dir(platform_data_dir: Path, user_id: str) -> Path:
    """Get user's video directory."""
    d = platform_data_dir / "users" / user_id / "videos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_video_package_available() -> None:
    """Check if skill_foundry_video is available."""
    try:
        from skill_foundry_video import VideoDownloader  # noqa: F401
    except ImportError as e:
        raise VideoIngestError(
            "skill_foundry_video package not installed. "
            "Install with: pip install -e packages/skill_foundry/skill_foundry_video"
        ) from e


def ingest_youtube_video(
    settings: Settings,
    user_id: str,
    youtube_url: str,
    *,
    start_sec: float | None = None,
    end_sec: float | None = None,
    max_duration_sec: float = 120.0,
) -> VideoIngestResult:
    """Download and store YouTube video for processing.

    Args:
        settings: Application settings
        user_id: User ID for workspace isolation
        youtube_url: YouTube video URL
        start_sec: Optional start time for trimming
        end_sec: Optional end time for trimming
        max_duration_sec: Maximum allowed video duration

    Returns:
        VideoIngestResult with video metadata

    Raises:
        VideoIngestError: If download fails or video is invalid
    """
    _ensure_video_package_available()

    from skill_foundry_video import VideoDownloader, VideoMetadata

    platform_data_dir = settings.resolved_platform_data_dir()
    output_dir = _user_videos_dir(platform_data_dir, user_id)

    video_uuid = str(uuid.uuid4())[:8]

    downloader = VideoDownloader(
        output_dir=output_dir,
        max_duration_sec=max_duration_sec,
        max_resolution=720,
    )

    try:
        metadata: VideoMetadata = downloader.download(
            youtube_url,
            start_sec=start_sec,
            end_sec=end_sec,
            filename=video_uuid,
        )
    except ValueError as e:
        raise VideoIngestError(str(e)) from e
    except RuntimeError as e:
        raise VideoIngestError(f"Download failed: {e}") from e

    artifact_relpath = metadata.file_path.relative_to(platform_data_dir)

    metadata_json = output_dir / f"{video_uuid}.meta.json"
    metadata_json.write_text(
        json.dumps(
            {
                "video_id": video_uuid,
                "youtube_video_id": metadata.video_id,
                "title": metadata.title,
                "duration_sec": metadata.duration_sec,
                "fps": metadata.fps,
                "width": metadata.width,
                "height": metadata.height,
                "file_path": str(artifact_relpath),
                "sha256": metadata.sha256,
                "source_url": metadata.source_url,
                "user_id": user_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    logger.info(
        "Ingested video %s for user %s: %.1fs @ %dfps",
        video_uuid,
        user_id,
        metadata.duration_sec,
        metadata.fps,
    )

    return VideoIngestResult(
        video_id=video_uuid,
        artifact_path=str(artifact_relpath),
        duration_sec=metadata.duration_sec,
        fps=metadata.fps,
        width=metadata.width,
        height=metadata.height,
        title=metadata.title,
        source_url=metadata.source_url,
    )


def get_video_metadata(
    settings: Settings,
    user_id: str,
    video_id: str,
) -> dict[str, Any] | None:
    """Get metadata for a previously ingested video.

    Args:
        settings: Application settings
        user_id: User ID
        video_id: Video ID from ingestion

    Returns:
        Video metadata dict or None if not found
    """
    platform_data_dir = settings.resolved_platform_data_dir()
    videos_dir = _user_videos_dir(platform_data_dir, user_id)
    metadata_path = videos_dir / f"{video_id}.meta.json"

    if not metadata_path.exists():
        return None

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        if data.get("user_id") != user_id:
            return None
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def get_video_file_path(
    settings: Settings,
    user_id: str,
    video_id: str,
) -> Path | None:
    """Get absolute path to video file.

    Args:
        settings: Application settings
        user_id: User ID
        video_id: Video ID from ingestion

    Returns:
        Absolute path to video file or None if not found
    """
    metadata = get_video_metadata(settings, user_id, video_id)
    if metadata is None:
        return None

    platform_data_dir = settings.resolved_platform_data_dir()
    video_path = platform_data_dir / metadata["file_path"]

    if not video_path.exists():
        return None

    return video_path
