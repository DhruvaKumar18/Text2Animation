import abc
import logging

logger = logging.getLogger(__name__)

class VideoProvider(abc.ABC):
    @abc.abstractproperty
    def provider_name(self) -> str:
        pass

    @abc.abstractproperty
    def model_name(self) -> str:
        pass

    @abc.abstractmethod
    def generate_video(self, prompt: str, duration: float) -> str:
        """
        Submits a video generation task using the prompt and duration.
        Returns a job_id or prediction_id (str).
        """
        pass

    @abc.abstractmethod
    def get_status(self, job_id: str) -> dict:
        """
        Checks the status of the generation task.
        Returns a dict: {
            "status": "PENDING" | "GENERATING" | "COMPLETED" | "FAILED",
            "video_url": str | None,
            "error": str | None,
            "raw_response": str
        }
        """
        pass

    def download_video(self, video_url: str, dest_path: str) -> bool:
        """
        Downloads the video from the video_url and saves it to dest_path.
        Returns True if successful, False otherwise.
        """
        import requests
        import os
        try:
            dir_name = os.path.dirname(dest_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            logger.info(f"Downloading video from {video_url} to {dest_path}...")
            response = requests.get(video_url, stream=True, timeout=60)
            response.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"Successfully downloaded video to {dest_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to download video from {video_url} to {dest_path}: {e}")
            return False
