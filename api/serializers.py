from rest_framework import serializers
from stories.models import Story, Scene, GeneratedVideo
from history.models import PipelineRunLog
from media_manager.models import MediaAsset

class PipelineRunLogSerializer(serializers.ModelSerializer):
    step_display = serializers.CharField(source='get_step_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PipelineRunLog
        fields = [
            'id', 'task_id', 'step', 'step_display', 'status', 'status_display',
            'log_message', 'error_traceback', 'started_at', 'duration_seconds'
        ]


class MediaAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaAsset
        fields = ['id', 'file', 'file_type', 'purpose', 'size_bytes', 'created_at']


class GeneratedVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedVideo
        fields = [
            'id', 'provider', 'model', 'prompt', 'video_file', 
            'external_job_id', 'status', 'duration', 'generation_time',
            'error_message', 'created_at', 'completed_at'
        ]


class SceneSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    generated_videos = GeneratedVideoSerializer(many=True, read_only=True)

    class Meta:
        model = Scene
        fields = [
            'id', 'scene_number', 'prompt', 'narration_text', 
            'image_file', 'video_file', 'duration', 'status', 'status_display', 'created_at',
            'title', 'description', 'characters', 'environment', 'lighting', 'mood',
            'camera_angle', 'image_prompt', 'animation_prompt',
            'image_seed', 'image_model', 'image_generation_time',
            'generated_videos'
        ]



class StorySerializer(serializers.ModelSerializer):
    scenes = SceneSerializer(many=True, read_only=True)
    logs = PipelineRunLogSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Story
        fields = [
            'id', 'title', 'prompt', 'status', 'status_display', 
            'final_video', 'created_at', 'updated_at', 'scenes', 'logs',
            'document_file', 'source_filename'
        ]


class CreateStorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Story
        fields = ['id', 'prompt', 'title', 'document_file', 'source_filename']
        extra_kwargs = {
            'prompt': {'required': True},
            'title': {'required': False},
            'document_file': {'required': False},
            'source_filename': {'required': False}
        }


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)

    def validate_file(self, value):
        # Validate file size (maximum 5MB)
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if value.size > max_size:
            raise serializers.ValidationError("File size exceeds the maximum limit of 5MB.")

        # Validate file format / extension
        import os
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = ['.pdf', '.docx', '.txt']
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Unsupported file format '{ext}'. Only PDF, DOCX, and TXT are supported."
            )
        return value
