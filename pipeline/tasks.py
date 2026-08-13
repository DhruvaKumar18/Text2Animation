import os
import time
import traceback
from celery import shared_task
from django.conf import settings

from stories.models import Story, Scene, GeneratedVideo
from history.models import PipelineRunLog
from media_manager.models import MediaAsset
from ai.services import generate_story_script
from ffmpeg_service.utils import stitch_videos
from ai.video_generation.manager import VideoGenerationManager

@shared_task(bind=True)
def run_story_generation_pipeline(self, story_id: int):
    """
    Celery task that orchestrates the Text-to-Animation pipeline:
    1. Prepares log registries.
    2. Generates storyboard script & scene text from the prompt.
    3. Initiates direct scene video generation asynchronously.
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

        # 3. Trigger Direct Video Generation Asynchronously
        create_log(
            PipelineRunLog.Step.DIRECT_VIDEO_GENERATION,
            PipelineRunLog.Status.RUNNING,
            f"Initiated direct video generation for {len(created_scenes)} scenes."
        )

        # Dispatch async task for each scene
        for scene in created_scenes:
            generate_scene_video.delay(scene.id)

        return f"Successfully initiated scene video generation for Story #{story_id}."

    except Exception as e:
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
        raise e


@shared_task(bind=True)
def generate_scene_video(self, scene_id: int):
    """
    Celery task that generates video for a single scene using the fallback sequence.
    """
    try:
        scene = Scene.objects.get(pk=scene_id)
    except Scene.DoesNotExist:
        return f"Scene #{scene_id} not found."

    story = scene.story
    scene.status = Scene.Status.GENERATING
    scene.save()

    # Define paths
    filename_base = f"story_{story.id}_scene_{scene.scene_number}"
    video_rel_path = f"animations/scenes/videos/{filename_base}.mp4"
    video_abs_path = os.path.join(settings.MEDIA_ROOT, video_rel_path)
    os.makedirs(os.path.dirname(video_abs_path), exist_ok=True)

    start_time = time.time()

    # Run generation manager
    manager = VideoGenerationManager()
    result = manager.generate_video_for_scene(scene, video_abs_path)
    generation_time = time.time() - start_time

    # Save GeneratedVideo record
    gen_video = GeneratedVideo.objects.create(
        scene=scene,
        provider=result["provider"],
        model=result["model"],
        prompt=result["prompt"],
        external_job_id=result["external_job_id"],
        status=result["status"],
        duration=scene.duration,
        generation_time=generation_time,
        api_response=result["raw_response"],
        error_message=result["error"]
    )

    if result["status"] == "COMPLETED":
        # Register in media field of scene
        scene.video_file.name = video_rel_path
        scene.status = Scene.Status.COMPLETED
        scene.save()

        # Register in Media Asset Manager
        MediaAsset.objects.create(
            file=video_rel_path,
            file_type=MediaAsset.FileType.VIDEO,
            purpose=f"Scene {scene.scene_number} Direct Video",
            story=story,
            scene=scene
        )
        
        # Save GeneratedVideo video_file field
        gen_video.video_file.name = video_rel_path
        gen_video.save()
        
        logger_message = f"Video generated successfully for Scene #{scene.scene_number} via {result['provider']}."
    else:
        scene.status = Scene.Status.FAILED
        scene.save()
        logger_message = f"Video generation failed for Scene #{scene.scene_number}. Error: {result['error']}"

    # Log individual result in pipeline log steps if necessary, or just track in general
    # Check if all scenes for the story are finished
    total_scenes = story.scenes.count()
    completed_scenes = story.scenes.filter(status=Scene.Status.COMPLETED).count()
    failed_scenes = story.scenes.filter(status=Scene.Status.FAILED).count()

    if completed_scenes + failed_scenes == total_scenes:
        # Resolve the step logs for DIRECT_VIDEO_GENERATION
        # Get active step logs for this story
        video_step_log = story.logs.filter(
            step=PipelineRunLog.Step.DIRECT_VIDEO_GENERATION,
            status=PipelineRunLog.Status.RUNNING
        ).last()

        if failed_scenes > 0:
            msg = f"Direct video generation complete with errors: {completed_scenes} succeeded, {failed_scenes} failed."
            if video_step_log:
                video_step_log.status = PipelineRunLog.Status.FAILED
                video_step_log.log_message = msg
                video_step_log.save()

            story.status = Story.Status.FAILED
            story.save()

            # Create failed pipeline log
            PipelineRunLog.objects.create(
                story=story,
                step=PipelineRunLog.Step.FAILED,
                status=PipelineRunLog.Status.FAILED,
                log_message="Animation pipeline failed because some scene videos failed to generate."
            )
        else:
            msg = f"Direct video generation complete for all {total_scenes} scenes."
            if video_step_log:
                video_step_log.status = PipelineRunLog.Status.SUCCESS
                video_step_log.log_message = msg
                video_step_log.save()

            # Start final rendering (stitching) task
            stitch_story_videos_task.delay(story.id)

    return logger_message


@shared_task(bind=True)
def stitch_story_videos_task(self, story_id: int):
    """
    Celery task that stitches completed scene videos into the final animation video.
    """
    task_id = self.request.id
    try:
        story = Story.objects.get(pk=story_id)
    except Story.DoesNotExist:
        return f"Story #{story_id} not found."

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

    pipeline_start_time = time.time()
    
    # 4. Concatenation / FFmpeg Stitching Step
    step_start = time.time()
    create_log(
        PipelineRunLog.Step.FFMPEG_STITCHING,
        PipelineRunLog.Status.RUNNING,
        "Stitching scene video clips into final animation..."
    )

    try:
        # Collect scene videos in order
        scenes = story.scenes.all().order_by("scene_number")
        scene_video_paths = []
        for scene in scenes:
            if scene.video_file:
                scene_video_paths.append(scene.video_file.path)
        
        if len(scene_video_paths) != len(scenes):
            raise ValueError(f"Missing video files for stitching. Found {len(scene_video_paths)} videos out of {len(scenes)} scenes.")

        final_video_rel_path = f"animations/completed/story_{story.id}_final.mp4"
        final_video_abs_path = os.path.join(settings.MEDIA_ROOT, final_video_rel_path)
        os.makedirs(os.path.dirname(final_video_abs_path), exist_ok=True)
        
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
        tb_str = traceback.format_exc()
        stitch_duration = time.time() - step_start
        
        create_log(
            PipelineRunLog.Step.FAILED,
            PipelineRunLog.Status.FAILED,
            f"Stitching failed: {str(e)}",
            duration=stitch_duration,
            error=tb_str
        )
        
        story.status = Story.Status.FAILED
        story.save()
        raise e
