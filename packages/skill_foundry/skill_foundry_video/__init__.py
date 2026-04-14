"""AUROSY Skill Foundry Video Processing - YouTube download and pose extraction."""

__version__ = "0.1.0"

from .downloader import VideoDownloader, VideoMetadata, download_youtube_video
from .pose_extractor import BatchPoseExtractor, PoseExtractionResult, extract_poses_from_video

__all__ = [
    "VideoDownloader",
    "VideoMetadata",
    "download_youtube_video",
    "BatchPoseExtractor",
    "PoseExtractionResult",
    "extract_poses_from_video",
]
