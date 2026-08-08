import random
import time
from PIL import Image, ImageDraw, ImageFont
import os
import subprocess
from django.conf import settings

def generate_story_script(prompt: str, story_id: int = None) -> list[dict]:
    """
    Splits the script into storyboard scenes using the LLM fallback chain.
    Standardizes output for Celery task compatibility.
    """
    from stories.services import SceneSplitterService
    scenes_data = SceneSplitterService.split_story_into_scenes(prompt, story_id)
    
    standardized = []
    for s in scenes_data:
        standardized.append({
            'scene_number': s.get('scene_number', 1),
            'prompt': s.get('image_prompt', s.get('prompt', 'Widescreen visual landscape')),
            'narration_text': s.get('narration', s.get('narration_text', '')),
            'duration': float(s.get('duration', 4.0)),
            
            # Extended cinematography attributes
            'title': s.get('title', f"Scene {s.get('scene_number', 1)}"),
            'description': s.get('description', ''),
            'characters': s.get('characters', ''),
            'environment': s.get('environment', ''),
            'lighting': s.get('lighting', ''),
            'mood': s.get('mood', ''),
            'camera_angle': s.get('camera_angle', ''),
            'image_prompt': s.get('image_prompt', ''),
            'animation_prompt': s.get('animation_prompt', '')
        })
        
    return standardized



def generate_scene_image(scene_or_prompt, scene_number_or_path = None, output_path: str = None) -> str:
    """
    Routes image generation to the ImageGeneratorService fallback chain.
    Supports both (prompt, scene_number, output_path) and (scene_instance, output_path) signatures.
    """
    from stories.services import ImageGeneratorService
    from stories.models import Scene

    if isinstance(scene_or_prompt, Scene):
        # New signature: (scene_instance, output_path)
        scene = scene_or_prompt
        path = scene_number_or_path
        ImageGeneratorService.generate_image_for_scene(scene, path)
        return path
    else:
        # Legacy signature: (prompt, scene_number, output_path)
        prompt = scene_or_prompt
        scene_number = scene_number_or_path
        
        # Create a transient, unsaved Scene container to pass downstream
        transient_scene = Scene(
            scene_number=scene_number,
            prompt=prompt
        )
        ImageGeneratorService.generate_image_for_scene(transient_scene, output_path)
        return output_path

