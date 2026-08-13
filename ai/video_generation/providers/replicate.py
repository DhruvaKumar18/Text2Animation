import requests
import json
import os
import time
import logging
from django.conf import settings
from ai.video_generation.base import VideoProvider

logger = logging.getLogger(__name__)

class ReplicateVideoProvider(VideoProvider):
    @property
    def provider_name(self) -> str:
        return "REPLICATE"

    @property
    def model_name(self) -> str:
        return "tencent/hunyuan-video"

    def _get_api_key(self) -> str:
        key = getattr(settings, 'REPLICATE_API_TOKEN', '') or os.environ.get('REPLICATE_API_TOKEN', '')
        if not key:
            raise ValueError("Replicate API token is missing. Please set REPLICATE_API_TOKEN environment variable.")
        return key

    def generate_video(self, prompt: str, duration: float) -> str:
        api_key = self._get_api_key()
        # Post to the model predictions URL to run the default/latest version
        url = f"https://api.replicate.com/v1/models/{self.model_name}/predictions"
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": {
                "prompt": prompt,
                "video_length": int(duration) if duration else 5
            }
        }

        for attempt in range(2):
            try:
                logger.info(f"[ReplicateVideoProvider] Submitting job to Replicate, prompt: {prompt[:50]}...")
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                if response.status_code == 404:
                    # Fallback to another popular hunyuan video model on Replicate if the tencent official one is not found
                    fallback_url = "https://api.replicate.com/v1/models/fofr/hunyuan-video/predictions"
                    logger.info(f"[ReplicateVideoProvider] Official model not found, falling back to: {fallback_url}")
                    response = requests.post(fallback_url, headers=headers, json=payload, timeout=20)
                
                response.raise_for_status()
                data = response.json()
                job_id = data.get("id")
                if not job_id:
                    raise ValueError(f"Invalid API response: {data}")
                logger.info(f"[ReplicateVideoProvider] Job submitted, prediction ID: {job_id}")
                return job_id
            except Exception as e:
                logger.warning(f"[ReplicateVideoProvider] Submit failed on attempt {attempt+1}: {e}")
                if attempt == 1:
                    raise e
                time.sleep(1)

    def get_status(self, job_id: str) -> dict:
        api_key = self._get_api_key()
        url = f"https://api.replicate.com/v1/predictions/{job_id}"
        headers = {
            "Authorization": f"Token {api_key}"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            raw_status = data.get("status")

            logger.info(f"[ReplicateVideoProvider] Status check for prediction {job_id}: {raw_status}")

            if raw_status in ["starting", "processing"]:
                return {
                    "status": "GENERATING",
                    "video_url": None,
                    "error": None,
                    "raw_response": json.dumps(data)
                }
            elif raw_status == "succeeded":
                output = data.get("output")
                # output can be a string or a list of strings on Replicate
                video_url = None
                if isinstance(output, list) and len(output) > 0:
                    video_url = output[0]
                elif isinstance(output, str):
                    video_url = output
                
                if not video_url:
                    raise ValueError(f"Could not extract video URL from output: {data}")

                return {
                    "status": "COMPLETED",
                    "video_url": video_url,
                    "error": None,
                    "raw_response": json.dumps(data)
                }
            else:
                # failed or canceled
                return {
                    "status": "FAILED",
                    "video_url": None,
                    "error": data.get("error", "Prediction failed or was canceled"),
                    "raw_response": json.dumps(data)
                }
        except Exception as e:
            logger.error(f"[ReplicateVideoProvider] Error polling status for prediction {job_id}: {e}")
            return {
                "status": "FAILED",
                "video_url": None,
                "error": str(e),
                "raw_response": str(e)
            }
