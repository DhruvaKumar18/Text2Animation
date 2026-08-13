import requests
import json
import os
import time
import logging
from django.conf import settings
from ai.video_generation.base import VideoProvider

logger = logging.getLogger(__name__)

class FalVideoProvider(VideoProvider):
    @property
    def provider_name(self) -> str:
        return "FAL_AI"

    @property
    def model_name(self) -> str:
        return "fal-ai/hunyuan-video"

    def _get_api_key(self) -> str:
        # Check both FAL_API_KEY and FAL_KEY per standard configurations
        key = getattr(settings, 'FAL_API_KEY', '') or getattr(settings, 'FAL_KEY', '') or os.environ.get('FAL_API_KEY', '') or os.environ.get('FAL_KEY', '')
        if not key:
            raise ValueError("Fal.ai API key is missing. Please set FAL_API_KEY or FAL_KEY environment variable.")
        return key

    def generate_video(self, prompt: str, duration: float) -> str:
        api_key = self._get_api_key()
        url = f"https://queue.fal.run/{self.model_name}"
        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json"
        }
        # Map duration (seconds) to hunyuan-video supported num_frames (85 or 129)
        # 85 frames is approx 3.5s, 129 frames is approx 5.4s
        num_frames = 85 if duration and duration <= 4.0 else 129

        payload = {
            "input": {
                "prompt": prompt,
                "num_frames": num_frames,
                "aspect_ratio": "16:9"
            }
        }

        # Handle request and retry if failed
        for attempt in range(2):
            try:
                logger.info(f"[FalVideoProvider] Submitting job, prompt: {prompt[:50]}...")
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                response.raise_for_status()
                data = response.json()
                request_id = data.get("request_id")
                if not request_id:
                    raise ValueError(f"Invalid API response: {data}")
                logger.info(f"[FalVideoProvider] Job submitted successfully, request_id: {request_id}")
                return request_id
            except Exception as e:
                logger.warning(f"[FalVideoProvider] Submit failed on attempt {attempt+1}: {e}")
                if attempt == 1:
                    raise e
                time.sleep(1)

    def get_status(self, job_id: str) -> dict:
        api_key = self._get_api_key()
        headers = {
            "Authorization": f"Key {api_key}"
        }
        
        status_url = f"https://queue.fal.run/requests/{job_id}/status"
        result_url = f"https://queue.fal.run/requests/{job_id}"

        try:
            # Step A: check status
            status_resp = requests.get(status_url, headers=headers, timeout=10)
            status_resp.raise_for_status()
            status_data = status_resp.json()
            raw_status = status_data.get("status")

            logger.info(f"[FalVideoProvider] Status check for {job_id}: {raw_status}")

            if raw_status in ["IN_QUEUE", "IN_PROGRESS"]:
                return {
                    "status": "GENERATING",
                    "video_url": None,
                    "error": None,
                    "raw_response": json.dumps(status_data)
                }
            elif raw_status == "COMPLETED":
                # Step B: fetch result
                result_resp = requests.get(result_url, headers=headers, timeout=10)
                result_resp.raise_for_status()
                result_data = result_resp.json()
                
                video_url = None
                # fal.ai hunyuan-video outputs: {"video": {"url": "..."}}
                if "video" in result_data and "url" in result_data["video"]:
                    video_url = result_data["video"]["url"]
                elif "images" in result_data and len(result_data["images"]) > 0: # support fallback format
                    video_url = result_data["images"][0].get("url")

                if not video_url:
                    raise ValueError(f"Could not extract video URL from results: {result_data}")

                return {
                    "status": "COMPLETED",
                    "video_url": video_url,
                    "error": None,
                    "raw_response": json.dumps(result_data)
                }
            else:
                # FAILED or other invalid state
                return {
                    "status": "FAILED",
                    "video_url": None,
                    "error": status_data.get("error", "Unknown API error"),
                    "raw_response": json.dumps(status_data)
                }
        except Exception as e:
            logger.error(f"[FalVideoProvider] Error polling status for {job_id}: {e}")
            return {
                "status": "FAILED",
                "video_url": None,
                "error": str(e),
                "raw_response": str(e)
            }
