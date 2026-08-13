import requests
import json
import os
import time
import logging
from django.conf import settings
from ai.video_generation.base import VideoProvider

logger = logging.getLogger(__name__)

class LumaVideoProvider(VideoProvider):
    @property
    def provider_name(self) -> str:
        return "LUMA_AI"

    @property
    def model_name(self) -> str:
        return "ray-2"

    def _get_api_key(self) -> str:
        key = getattr(settings, 'LUMA_API_KEY', '') or os.environ.get('LUMA_API_KEY', '')
        if not key:
            raise ValueError("Luma AI API key is missing. Please set LUMA_API_KEY environment variable.")
        return key

    def generate_video(self, prompt: str, duration: float) -> str:
        api_key = self._get_api_key()
        url = "https://api.lumalabs.ai/dream-machine/v1/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "model": self.model_name
        }

        for attempt in range(2):
            try:
                logger.info(f"[LumaVideoProvider] Submitting job to Luma AI, prompt: {prompt[:50]}...")
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                response.raise_for_status()
                data = response.json()
                job_id = data.get("id")
                if not job_id:
                    raise ValueError(f"Invalid API response: {data}")
                logger.info(f"[LumaVideoProvider] Job submitted successfully, generation ID: {job_id}")
                return job_id
            except Exception as e:
                logger.warning(f"[LumaVideoProvider] Submit failed on attempt {attempt+1}: {e}")
                if attempt == 1:
                    raise e
                time.sleep(1)

    def get_status(self, job_id: str) -> dict:
        api_key = self._get_api_key()
        url = f"https://api.lumalabs.ai/dream-machine/v1/generations/{job_id}"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            raw_state = data.get("state")

            logger.info(f"[LumaVideoProvider] Status check for Luma ID {job_id}: {raw_state}")

            if raw_state in ["queued", "processing"]:
                return {
                    "status": "GENERATING",
                    "video_url": None,
                    "error": None,
                    "raw_response": json.dumps(data)
                }
            elif raw_state == "completed":
                assets = data.get("assets", {})
                video_url = assets.get("video")
                if not video_url:
                    raise ValueError(f"Could not find video URL in completed assets: {data}")
                return {
                    "status": "COMPLETED",
                    "video_url": video_url,
                    "error": None,
                    "raw_response": json.dumps(data)
                }
            else:
                # failed
                return {
                    "status": "FAILED",
                    "video_url": None,
                    "error": data.get("failure_reason", "Luma generation failed"),
                    "raw_response": json.dumps(data)
                }
        except Exception as e:
            logger.error(f"[LumaVideoProvider] Error polling status for Luma ID {job_id}: {e}")
            return {
                "status": "FAILED",
                "video_url": None,
                "error": str(e),
                "raw_response": str(e)
            }
