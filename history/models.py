from django.db import models
from stories.models import Story

class PipelineRunLog(models.Model):
    class Step(models.TextChoices):
        STORY_INITIALIZATION = 'STORY_INITIALIZATION', 'Story Initialization'
        SCRIPT_GENERATION = 'SCRIPT_GENERATION', 'Script & Scenes Generation'
        DIRECT_VIDEO_GENERATION = 'DIRECT_VIDEO_GENERATION', 'Direct Video Generation'
        NARRATION = 'NARRATION', 'Narration Track Generation'
        BACKGROUND_MUSIC = 'BACKGROUND_MUSIC', 'Background Music Integration'
        FFMPEG_STITCHING = 'FFMPEG_STITCHING', 'FFmpeg Video Stitching'
        COMPLETED = 'COMPLETED', 'Pipeline Completed'
        FAILED = 'FAILED', 'Pipeline Failed'

    class Status(models.TextChoices):
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='logs')
    task_id = models.CharField(max_length=255, blank=True, null=True, help_text="Celery task UUID")
    step = models.CharField(max_length=50, choices=Step.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    log_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['story', 'started_at']

    def __str__(self):
        return f"{self.story_id} - {self.step} - {self.status}"


class LlmApiLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    story = models.ForeignKey(Story, on_delete=models.SET_NULL, null=True, blank=True, related_name='llm_logs')
    provider = models.CharField(max_length=50) # GEMINI, GROQ, OPENROUTER, MOCK
    prompt = models.TextField()
    response_text = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)
    error_message = models.TextField(blank=True, null=True)
    execution_time_seconds = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider} - {self.status} - {self.created_at}"

