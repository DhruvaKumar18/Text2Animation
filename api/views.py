from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from stories.models import Story, Scene
from history.models import PipelineRunLog
from pipeline.tasks import run_story_generation_pipeline
from api.serializers import (
    StorySerializer, 
    CreateStorySerializer,
    SceneSerializer, 
    PipelineRunLogSerializer,
    DocumentUploadSerializer
)

class StoryViewSet(viewsets.ModelViewSet):
    queryset = Story.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateStorySerializer
        return StorySerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        story = serializer.save()
        
        # Trigger Celery pipeline asynchronously
        run_story_generation_pipeline.delay(story.id)
        
        # Return serialized details of the newly created story
        headers = self.get_success_headers(serializer.data)
        full_serializer = StorySerializer(story)
        return Response(full_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['post'], url_path='parse-document')
    def parse_document(self, request):
        """
        Receives an uploaded script document (PDF, DOCX, TXT), validates it,
        extracts and cleans its text, and returns it.
        """
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data['file']
        
        try:
            from stories.services import DocumentParserService
            extracted_text = DocumentParserService.parse_document(uploaded_file, uploaded_file.name)
            return Response({
                'text': extracted_text,
                'filename': uploaded_file.name
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': f"Failed to extract document contents: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='polish')
    def polish_prompt(self, request):
        """
        Receives an original prompt text, executes it through the LLM fallback chain,
        and returns the polished text result.
        """
        prompt_text = request.data.get('prompt', '').strip()
        story_id = request.data.get('story_id', None)
        
        if not prompt_text:
            return Response({'error': 'Original prompt content is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            from stories.services import StoryPolisherService
            result = StoryPolisherService.polish_story_text(prompt_text, story_id)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f"Failed to run polishing engine: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='split')
    def split_prompt(self, request):
        """
        Receives an original prompt text, splits it into structured cinematic scenes,
        using the LLM fallback chain, and returns the list of scenes.
        """
        prompt_text = request.data.get('prompt', '').strip()
        story_id = request.data.get('story_id', None)
        
        if not prompt_text:
            return Response({'error': 'Original prompt content is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            from stories.services import SceneSplitterService
            result = SceneSplitterService.split_story_into_scenes(prompt_text, story_id)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f"Failed to run scene splitting engine: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)



    @action(detail=True, methods=['post'], url_path='retry')
    def retry_pipeline(self, request, pk=None):
        """
        Re-triggers the pipeline task for a story that failed or is in draft.
        """
        story = self.get_object()
        if story.status in [Story.Status.FAILED, Story.Status.DRAFT, Story.Status.COMPLETED]:
            story.status = Story.Status.DRAFT
            story.save()
            run_story_generation_pipeline.delay(story.id)
            return Response({'status': 'Animation pipeline re-triggered successfully.'}, status=status.HTTP_200_OK)
        return Response({'error': 'Cannot retry a pipeline that is already processing.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='generate-videos')
    def generate_videos_endpoint(self, request, pk=None):
        """
        Manually triggers direct video generation for all scenes of the story.
        """
        story = self.get_object()
        if story.status == Story.Status.PROCESSING:
            return Response({'error': 'Pipeline is already processing this story.'}, status=status.HTTP_400_BAD_REQUEST)

        story.status = Story.Status.PROCESSING
        story.save()

        # Reset scenes to PENDING status
        story.scenes.update(status=Scene.Status.PENDING)

        # Log direct video generation step
        PipelineRunLog.objects.create(
            story=story,
            step=PipelineRunLog.Step.DIRECT_VIDEO_GENERATION,
            status=PipelineRunLog.Status.RUNNING,
            log_message=f"Initiated direct video generation for {story.scenes.count()} scenes."
        )

        from pipeline.tasks import generate_scene_video
        for scene in story.scenes.all():
            generate_scene_video.delay(scene.id)

        return Response({'status': 'Direct video generation initiated.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='generate-scene-image')
    def generate_scene_image_endpoint(self, request, pk=None):
        """
        Manually triggers the fallback image generation chain for a specific scene of this story.
        Useful for regenerating images.
        """
        story = self.get_object()
        scene_number = request.data.get('scene_number')
        
        if not scene_number:
            return Response({'error': 'scene_number is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            scene = story.scenes.get(scene_number=scene_number)
        except Scene.DoesNotExist:
            return Response({'error': f'Scene #{scene_number} not found for this story.'}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            import os
            from django.conf import settings
            from ai.services import generate_scene_image
            
            filename_base = f"story_{story.id}_scene_{scene.scene_number}"
            img_rel_path = f"animations/scenes/images/{filename_base}.jpg"
            img_abs_path = os.path.join(settings.MEDIA_ROOT, img_rel_path)
            
            generate_scene_image(scene, img_abs_path)
            
            from api.serializers import SceneSerializer
            return Response({
                'message': f'Successfully generated image for scene #{scene_number}.',
                'scene': SceneSerializer(scene).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Failed to generate image: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='generate-scene-video')
    def generate_scene_video_endpoint(self, request, pk=None):
        """
        Manually triggers direct video generation for a specific scene of this story.
        Useful for regenerating/retrying video generation for a single scene.
        """
        story = self.get_object()
        scene_number = request.data.get('scene_number')
        
        if not scene_number:
            return Response({'error': 'scene_number is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            scene = story.scenes.get(scene_number=scene_number)
        except Scene.DoesNotExist:
            return Response({'error': f'Scene #{scene_number} not found for this story.'}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            # Set scene status to GENERATING
            scene.status = Scene.Status.GENERATING
            scene.save()
            
            # Reset the story's status to PROCESSING so the dashboard UI polls and updates
            if story.status != Story.Status.PROCESSING:
                story.status = Story.Status.PROCESSING
                story.save()
                
            # Log single scene video regeneration in PipelineRunLog
            PipelineRunLog.objects.create(
                story=story,
                step=PipelineRunLog.Step.DIRECT_VIDEO_GENERATION,
                status=PipelineRunLog.Status.RUNNING,
                log_message=f"Manually re-triggered video generation for Scene #{scene_number}."
            )
            
            # Trigger Celery task asynchronously
            from pipeline.tasks import generate_scene_video
            generate_scene_video.delay(scene.id)
            
            from api.serializers import SceneSerializer
            return Response({
                'message': f'Successfully initiated video regeneration for scene #{scene_number}.',
                'scene': SceneSerializer(scene).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Failed to trigger video generation: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)



class SceneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Scene.objects.all()
    serializer_class = SceneSerializer
    filterset_fields = ['story']


class PipelineRunLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PipelineRunLog.objects.all()
    serializer_class = PipelineRunLogSerializer
    filterset_fields = ['story']
