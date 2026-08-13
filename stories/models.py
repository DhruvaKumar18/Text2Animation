from django.db import models

class Story(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    title = models.CharField(max_length=255, blank=True)
    prompt = models.TextField(help_text="The main textual story prompt entered by the user")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    final_video = models.FileField(
        upload_to='animations/completed/',
        null=True,
        blank=True,
        help_text="The fully stitched animation video file"
    )
    document_file = models.FileField(
        upload_to='uploads/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text="Uploaded story script file (PDF, DOCX, TXT)"
    )
    source_filename = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original filename of the uploaded document"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Stories"

    def __str__(self):
        return self.title or f"Story #{self.id}"


class Scene(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Waiting'
        GENERATING = 'GENERATING', 'Generating'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    story = models.ForeignKey(
        Story,
        related_name='scenes',
        on_delete=models.CASCADE
    )
    scene_number = models.PositiveIntegerField()
    prompt = models.TextField(help_text="Visual prompt for this specific scene")
    narration_text = models.TextField(help_text="Speech or narration text overlay for this scene")
    image_file = models.ImageField(
        upload_to='animations/scenes/images/',
        null=True,
        blank=True,
        help_text="Generated image asset for the scene"
    )
    video_file = models.FileField(
        upload_to='animations/scenes/videos/',
        null=True,
        blank=True,
        help_text="Generated video clip for the scene"
    )
    duration = models.FloatField(
        default=4.0,
        help_text="Duration of this scene in seconds"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Title of the scene"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Detailed description of scene action"
    )
    characters = models.TextField(
        blank=True,
        null=True,
        help_text="Characters involved in this scene"
    )
    environment = models.TextField(
        blank=True,
        null=True,
        help_text="Setting or location details"
    )
    lighting = models.TextField(
        blank=True,
        null=True,
        help_text="Lighting description"
    )
    mood = models.TextField(
        blank=True,
        null=True,
        help_text="Emotional tone of the scene"
    )
    camera_angle = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Camera shot type and angle"
    )
    image_prompt = models.TextField(
        blank=True,
        null=True,
        help_text="Detailed visual prompt used for image rendering"
    )
    animation_prompt = models.TextField(
        blank=True,
        null=True,
        help_text="Prompt detailing camera movement or video motion"
    )
    image_seed = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Generation seed value used for reproducibility"
    )
    image_model = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="AI model name used to generate this image"
    )
    image_generation_time = models.FloatField(
        null=True,
        blank=True,
        help_text="Time taken to generate the image in seconds"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['story', 'scene_number']

    def __str__(self):
        return f"Scene #{self.scene_number} for Story {self.story_id}"


class GeneratedVideo(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        GENERATING = 'GENERATING', 'Generating'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name='generated_videos'
    )
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    prompt = models.TextField()
    video_file = models.FileField(
        upload_to='animations/scenes/videos/',
        null=True,
        blank=True,
        help_text="Locally downloaded generated video file"
    )
    external_job_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    duration = models.FloatField(null=True, blank=True)
    resolution = models.CharField(max_length=20, blank=True, null=True)
    fps = models.IntegerField(null=True, blank=True)
    generation_time = models.FloatField(null=True, blank=True, help_text="Total API execution time in seconds")
    api_response = models.TextField(blank=True, null=True, help_text="Raw API JSON response text")
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Video for Scene {self.scene.scene_number} ({self.provider}) - {self.status}"
