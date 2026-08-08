from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from stories.models import Story, Scene

class ApiTestCase(APITestCase):
    def setUp(self):
        self.story = Story.objects.create(
            title="Old Story",
            prompt="Draft prompt to test status checks",
            status=Story.Status.FAILED
        )

    @patch('pipeline.tasks.run_story_generation_pipeline.delay')
    def test_create_story_triggers_pipeline(self, mock_delay):
        """Creating a story via POST should trigger Celery tasks pipeline and return HTTP 201."""
        url = reverse('story-list')
        data = {
            'title': 'New Test Story',
            'prompt': 'A programmer creating a masterpiece animation'
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'New Test Story')
        self.assertTrue(Story.objects.filter(title='New Test Story').exists())
        
        # Verify task is scheduled with correct story id
        new_story = Story.objects.get(title='New Test Story')
        mock_delay.assert_called_once_with(new_story.id)

    @patch('pipeline.tasks.run_story_generation_pipeline.delay')
    def test_retry_pipeline_trigger(self, mock_delay):
        """Retrying a failed story pipeline should reset state to DRAFT and schedule Celery worker."""
        url = reverse('story-retry-pipeline', kwargs={'pk': self.story.id})
        response = self.client.post(url, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.story.refresh_from_db()
        self.assertEqual(self.story.status, Story.Status.DRAFT)
        mock_delay.assert_called_once_with(self.story.id)

    def test_parse_document_endpoint_success(self):
        """Uploading a valid txt file should return the extracted and cleaned text content."""
        import io
        url = reverse('story-parse-document')
        
        # Create a mock text file stream
        file_data = io.BytesIO(b"Once upon a time, there was a test case.")
        file_data.name = 'test_story.txt'
        
        response = self.client.post(url, {'file': file_data}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['text'], "Once upon a time, there was a test case.")
        self.assertEqual(response.data['filename'], "test_story.txt")

    def test_parse_document_endpoint_invalid_format(self):
        """Uploading an unsupported file type (like png) should fail with validation error."""
        import io
        url = reverse('story-parse-document')
        
        file_data = io.BytesIO(b"\x89PNG\r\n\x1a\n...")
        file_data.name = 'fake_image.png'
        
        response = self.client.post(url, {'file': file_data}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_parse_document_endpoint_file_too_large(self):
        """Uploading a file exceeding 5MB should fail with a size limit validation error."""
        import io
        url = reverse('story-parse-document')
        
        # 5MB + 1 byte
        large_data = b"x" * (5 * 1024 * 1024 + 1)
        file_data = io.BytesIO(large_data)
        file_data.name = 'huge_script.txt'
        
        response = self.client.post(url, {'file': file_data}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_polish_prompt_endpoint_success(self):
        """API request to polish prompt should run fallback chain and return enhanced text."""
        url = reverse('story-polish-prompt')
        data = {'prompt': 'astronaut car landscape'}
        
        with patch.dict('os.environ', {'GEMINI_API_KEY': '', 'GROQ_API_KEY': '', 'OPENROUTER_API_KEY': ''}, clear=True):
            response = self.client.post(url, data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['provider'], 'MOCK')
            self.assertIn('Cinematic space explorer', response.data['polished_text'])
            self.assertIn('hovercraft', response.data['polished_text'])
            self.assertIn('visual vistas', response.data['polished_text'])
            self.assertTrue('execution_time' in response.data)

    def test_polish_prompt_endpoint_missing_prompt(self):
        """API request without prompt parameter should return HTTP 400 Bad Request."""
        url = reverse('story-polish-prompt')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_split_prompt_endpoint_success(self):
        """API request to split prompt should run fallback chain and return structured scenes."""
        url = reverse('story-split-prompt')
        data = {'prompt': 'The astronaut floats in space.\nA giant spacecraft emerges.'}
        
        with patch.dict('os.environ', {'GEMINI_API_KEY': '', 'GROQ_API_KEY': '', 'OPENROUTER_API_KEY': ''}, clear=True):
            response = self.client.post(url, data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data), 2)
            self.assertEqual(response.data[0]['scene_number'], 1)
            self.assertEqual(response.data[0]['title'], "The Astronaut Floats")
            self.assertEqual(response.data[1]['title'], "A Giant Spacecraft")
            self.assertEqual(response.data[0]['characters'], "Cinematic space explorer")

    def test_split_prompt_endpoint_missing_prompt(self):
        """API request to split without prompt should return HTTP 400 Bad Request."""
        url = reverse('story-split-prompt')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_generate_scene_image_endpoint_success(self):
        """API request to manually generate a scene's image should succeed and return metadata."""
        story = Story.objects.create(prompt="Space explorer.")
        Scene.objects.create(story=story, scene_number=1, prompt="Widescreen space astronaut.")
        
        url = reverse('story-generate-scene-image-endpoint', args=[story.id])
        data = {'scene_number': 1}
        
        with patch.dict('os.environ', {'HF_API_KEY': '', 'FAL_KEY': '', 'REPLICATE_API_TOKEN': ''}, clear=True):
            response = self.client.post(url, data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['scene']['scene_number'], 1)
            self.assertEqual(response.data['scene']['image_model'], 'MOCK_PILLOW')

    def test_generate_scene_image_endpoint_missing_parameters(self):
        """API request without scene_number should return HTTP 400 Bad Request."""
        story = Story.objects.create(prompt="Space explorer.")
        url = reverse('story-generate-scene-image-endpoint', args=[story.id])
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)




