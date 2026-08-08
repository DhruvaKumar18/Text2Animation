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
        PENDING = 'PENDING', 'Pending'
        GENERATING_ASSETS = 'GENERATING_ASSETS', 'Generating Assets'
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
