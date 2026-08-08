import os
import time
import traceback
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from stories.models import Story, Scene
from history.models import PipelineRunLog
from media_manager.models import MediaAsset
from ai.services import generate_story_script, generate_scene_image
from ffmpeg_service.utils import convert_image_to_video, add_text_caption_to_video, stitch_videos

@shared_task(bind=True)
def run_story_generation_pipeline(self, story_id: int):
    """
    Celery task that orchestrates the entire Text-to-Animation pipeline:
    1. Generates storyboard script & scene text from the prompt.
    2. Renders scene image assets using Pillow.
    3. Converts image assets to video clips using FFmpeg.
    4. Overlays subtitles onto the video clips.
    5. Concatenates/stitches the clips into the final animation video.
    """
    task_id = self.request.id
    
    try:
        story = Story.objects.get(pk=story_id)
    except Story.DoesNotExist:
        return f"Story #{story_id} not found."

    story.status = Story.Status.PROCESSING
    story.save()

    def create_log(step, status, message="", duration=None, error=""):
        return PipelineRunLog.objects.create(
            story=story,
            task_id=task_id,
            step=step,
            status=status,
            log_message=message,
            duration_seconds=duration,
            error_traceback=error
        )

    # 1. Pipeline Start
    pipeline_start_time = time.time()
    create_log(
        PipelineRunLog.Step.STORY_INITIALIZATION,
        PipelineRunLog.Status.SUCCESS,
        "Animation pipeline started successfully."
    )

    try:
        # 2. Script & Scenes Generation
        step_start = time.time()
        create_log(
            PipelineRunLog.Step.SCRIPT_GENERATION,
            PipelineRunLog.Status.RUNNING,
            "Generating storyboards and script details via AI..."
        )
        
        scenes_data = generate_story_script(story.prompt, story_id=story.id)
        
        # Determine a title from the prompt if none is set
        if not story.title:
            words = story.prompt.split()
            story.title = " ".join(words[:4]).title() + " Animation"
            story.save()

        # Delete existing scenes if any (re-run support)
        story.scenes.all().delete()
        
        created_scenes = []
        for s in scenes_data:
            scene = Scene.objects.create(
                story=story,
                scene_number=s['scene_number'],
                prompt=s['prompt'],
                narration_text=s['narration_text'],
                duration=s['duration'],
                status=Scene.Status.PENDING,
                title=s.get('title', ''),
                description=s.get('description', ''),
                characters=s.get('characters', ''),
                environment=s.get('environment', ''),
                lighting=s.get('lighting', ''),
                mood=s.get('mood', ''),
                camera_angle=s.get('camera_angle', ''),
                image_prompt=s.get('image_prompt', ''),
                animation_prompt=s.get('animation_prompt', '')
            )
            created_scenes.append(scene)
            
        step_duration = time.time() - step_start
        create_log(
            PipelineRunLog.Step.SCRIPT_GENERATION,
            PipelineRunLog.Status.SUCCESS,
            f"Generated {len(created_scenes)} scenes from prompt.",
            duration=step_duration
        )

        # 3. Scene Asset Generation (Image + Video Clips)
        scene_video_paths = []
        
        for scene in created_scenes:
            scene.status = Scene.Status.GENERATING_ASSETS
            scene.save()
            
            # --- Image Generation Step ---
            step_start = time.time()
            create_log(
                PipelineRunLog.Step.IMAGE_GENERATION,
                PipelineRunLog.Status.RUNNING,
                f"Generating image asset for Scene #{scene.scene_number}..."
            )
            
            # Define file paths
            filename_base = f"story_{story.id}_scene_{scene.scene_number}"
            img_rel_path = f"animations/scenes/images/{filename_base}.jpg"
            img_abs_path = os.path.join(settings.MEDIA_ROOT, img_rel_path)
            
            # Generate the scene image
            generate_scene_image(scene, img_abs_path)
            scene.image_file.name = img_rel_path
            scene.save()
            
            # Register in Media Asset Manager
            MediaAsset.objects.create(
                file=img_rel_path,
                file_type=MediaAsset.FileType.IMAGE,
                purpose=f"Scene {scene.scene_number} Image",
                story=story,
                scene=scene
            )
            
            img_duration = time.time() - step_start
            create_log(
                PipelineRunLog.Step.IMAGE_GENERATION,
                PipelineRunLog.Status.SUCCESS,
                f"Image asset for Scene #{scene.scene_number} saved.",
                duration=img_duration
            )

            # --- Video Clip Generation & Subtitle Overlay Step ---
            step_start = time.time()
            create_log(
                PipelineRunLog.Step.VIDEO_GENERATION,
                PipelineRunLog.Status.RUNNING,
                f"Rendering video clip and overlaying subtitles for Scene #{scene.scene_number}..."
            )
            
            raw_video_rel_path = f"animations/scenes/videos/{filename_base}_raw.mp4"
            raw_video_abs_path = os.path.join(settings.MEDIA_ROOT, raw_video_rel_path)
            
            captioned_video_rel_path = f"animations/scenes/videos/{filename_base}_captioned.mp4"
            captioned_video_abs_path = os.path.join(settings.MEDIA_ROOT, captioned_video_rel_path)
            
            # Step A: Image to raw video clip
            convert_image_to_video(img_abs_path, raw_video_abs_path, scene.duration)
            
            # Step B: Add narration subtitles
            add_text_caption_to_video(raw_video_abs_path, captioned_video_abs_path, scene.narration_text)
            
            # Store final scene video
            scene.video_file.name = captioned_video_rel_path
            scene.status = Scene.Status.COMPLETED
            scene.save()
            
            # Register in Media Asset Manager
            MediaAsset.objects.create(
                file=captioned_video_rel_path,
                file_type=MediaAsset.FileType.VIDEO,
                purpose=f"Scene {scene.scene_number} Video Clip",
                story=story,
                scene=scene
            )
            
            # Clean up intermediate raw clip to save space
            if os.path.exists(raw_video_abs_path):
                try:
                    os.remove(raw_video_abs_path)
                except Exception:
                    pass
            
            scene_video_paths.append(captioned_video_abs_path)
            
            video_duration = time.time() - step_start
            create_log(
                PipelineRunLog.Step.VIDEO_GENERATION,
                PipelineRunLog.Status.SUCCESS,
                f"Video clip for Scene #{scene.scene_number} completed.",
                duration=video_duration
            )

        # 4. Concatenation / FFmpeg Stitching Step
        step_start = time.time()
        create_log(
            PipelineRunLog.Step.FFMPEG_STITCHING,
            PipelineRunLog.Status.RUNNING,
            f"Stitching {len(scene_video_paths)} scene video clips into final animation..."
        )
        
        final_video_rel_path = f"animations/completed/story_{story.id}_final.mp4"
        final_video_abs_path = os.path.join(settings.MEDIA_ROOT, final_video_rel_path)
        
        stitch_success = stitch_videos(scene_video_paths, final_video_abs_path)
        
        if not stitch_success:
            raise RuntimeError("FFmpeg stitching process returned a failure status code.")
            
        story.final_video.name = final_video_rel_path
        story.status = Story.Status.COMPLETED
        story.save()
        
        # Register in Media Asset Manager
        MediaAsset.objects.create(
            file=final_video_rel_path,
            file_type=MediaAsset.FileType.VIDEO,
            purpose="Stitched Final Video Animation",
            story=story
        )
        
        stitch_duration = time.time() - step_start
        create_log(
            PipelineRunLog.Step.FFMPEG_STITCHING,
            PipelineRunLog.Status.SUCCESS,
            "Video stitched and finalized successfully.",
            duration=stitch_duration
        )

        # 5. Pipeline Complete
        total_duration = time.time() - pipeline_start_time
        create_log(
            PipelineRunLog.Step.COMPLETED,
            PipelineRunLog.Status.SUCCESS,
            f"Full pipeline run completed in {total_duration:.2f} seconds.",
            duration=total_duration
        )
        
        return f"Successfully generated final animation for Story #{story_id}."

    except Exception as e:
        # Error handling / Pipeline Failure
        tb_str = traceback.format_exc()
        total_duration = time.time() - pipeline_start_time
        
        create_log(
            PipelineRunLog.Step.FAILED,
            PipelineRunLog.Status.FAILED,
            f"Pipeline failed: {str(e)}",
            duration=total_duration,
            error=tb_str
        )
        
        story.status = Story.Status.FAILED
        story.save()
        
        # Update any in-progress scene to failed
        story.scenes.filter(status=Scene.Status.GENERATING_ASSETS).update(status=Scene.Status.FAILED)
        
        raise e
