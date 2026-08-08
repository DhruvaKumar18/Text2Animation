from django.db import models
from stories.models import Story, Scene

class MediaAsset(models.Model):
    class FileType(models.TextChoices):
        IMAGE = 'IMAGE', 'Image'
        VIDEO = 'VIDEO', 'Video'
        AUDIO = 'AUDIO', 'Audio'

    file = models.FileField(upload_to='media_assets/%Y/%m/%d/')
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    purpose = models.CharField(max_length=50, blank=True, help_text="e.g. scene_background, character, soundtrack")
    story = models.ForeignKey(Story, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets')
    scene = models.ForeignKey(Scene, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets')
    size_bytes = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Automatically calculate file size if available before saving
        if self.file and (self.size_bytes is None or self.size_bytes == 0):
            try:
                self.size_bytes = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Asset #{self.id} ({self.file_type}) - {self.file.name}"
