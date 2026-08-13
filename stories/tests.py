from django.test import TestCase
from stories.models import Story, Scene

class StoriesModelsTestCase(TestCase):
    def setUp(self):
        self.story = Story.objects.create(
            title="Cosmic Voyage",
            prompt="A ship sailing into the stars"
        )
        self.scene1 = Scene.objects.create(
            story=self.story,
            scene_number=1,
            prompt="The ship takes off from earth",
            narration_text="The engines roared as the voyage began.",
            duration=3.5
        )
        self.scene2 = Scene.objects.create(
            story=self.story,
            scene_number=2,
            prompt="Sailing past Mars",
            narration_text="Mars casted a deep red shadow on the ship.",
            duration=4.0
        )

    def test_story_creation(self):
        """Verify story attributes and default status."""
        self.assertEqual(self.story.title, "Cosmic Voyage")
        self.assertEqual(self.story.status, Story.Status.DRAFT)
        self.assertEqual(str(self.story), "Cosmic Voyage")

    def test_scene_relationship(self):
        """Verify scenes are correctly related to the story and ordered by scene_number."""
        scenes = self.story.scenes.all()
        self.assertEqual(scenes.count(), 2)
        self.assertEqual(scenes[0], self.scene1)
        self.assertEqual(scenes[1], self.scene2)
        self.assertEqual(str(self.scene1), f"Scene #1 for Story {self.story.id}")


class DocumentParserTestCase(TestCase):
    def test_text_cleaning(self):
        """Verify duplicate whitespaces are collapsed, and page headers/footers are stripped."""
        from stories.services import DocumentParserService
        
        dirty_text = (
            "Once upon a time, in a far  away kingdom...\n"
            "  Page 1  \n"
            "\n"
            "\n"
            "A brave knight set out on a quest.\n"
            "12 / 100\n"
            "The end."
        )
        
        expected_cleaned = (
            "Once upon a time, in a far away kingdom...\n"
            "\n"
            "A brave knight set out on a quest.\n"
            "The end."
        )
        
        cleaned = DocumentParserService.clean_text(dirty_text)
        self.assertEqual(cleaned, expected_cleaned)

    def test_txt_extraction(self):
        """Verify plain text file stream extraction works correctly."""
        import io
        from stories.services import DocumentParserService
        
        text_bytes = b"Hello, this is a plain text file."
        file_obj = io.BytesIO(text_bytes)
        
        extracted = DocumentParserService.parse_document(file_obj, "test.txt")
        self.assertEqual(extracted, "Hello, this is a plain text file.")


from unittest.mock import patch, MagicMock
from history.models import LlmApiLog
from stories.services import StoryPolisherService

class StoryPolisherTestCase(TestCase):
    @patch('requests.post')
    def test_gemini_success_primary(self, mock_post):
        """Verify Gemini executes successfully as the primary provider and logs outcomes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{'text': 'Polished by Gemini! Once upon a time.'}]
                }
            }]
        }
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'gemini_test_key'}):
            result = StoryPolisherService.polish_story_text("Once upon a time.")
            
            self.assertEqual(result['polished_text'], "Polished by Gemini! Once upon a time.")
            self.assertEqual(result['provider'], "GEMINI")
            
            # Check db logs
            logs = LlmApiLog.objects.filter(provider="GEMINI")
            self.assertEqual(logs.count(), 1)
            self.assertEqual(logs.first().status, LlmApiLog.Status.SUCCESS)

    @patch('requests.post')
    def test_gemini_fail_groq_success(self, mock_post):
        """Verify Groq is executed if Gemini fails and logs are correctly structured."""
        gemini_response = MagicMock()
        gemini_response.raise_for_status.side_effect = Exception("Gemini server error")
        
        groq_response = MagicMock()
        groq_response.status_code = 200
        groq_response.json.return_value = {
            'choices': [{
                'message': {'content': 'Polished by Groq! A knight on a horse.'}
            }]
        }
        
        mock_post.side_effect = [gemini_response, groq_response]

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'gem_key', 'GROQ_API_KEY': 'groq_key'}):
            result = StoryPolisherService.polish_story_text("A knight on a horse.")
            
            self.assertEqual(result['polished_text'], "Polished by Groq! A knight on a horse.")
            self.assertEqual(result['provider'], "GROQ")
            
            # Check db logs for both providers
            self.assertTrue(LlmApiLog.objects.filter(provider="GEMINI", status=LlmApiLog.Status.FAILED).exists())
            self.assertTrue(LlmApiLog.objects.filter(provider="GROQ", status=LlmApiLog.Status.SUCCESS).exists())

    def test_mock_fallback_no_keys(self):
        """Verify rule-based mock enhancer functions properly when no keys are supplied."""
        with self.settings(GEMINI_API_KEY='', GROQ_API_KEY='', OPENROUTER_API_KEY=''):
            with patch.dict('os.environ', {'GEMINI_API_KEY': '', 'GROQ_API_KEY': '', 'OPENROUTER_API_KEY': ''}, clear=True):
                result = StoryPolisherService.polish_story_text("A astronaut saw a car in the city.")
                
                # Verify replacements mapping works
                self.assertIn("cinematic space explorer", result['polished_text'])
                self.assertIn("hovercraft", result['polished_text'])
                self.assertIn("metropolis", result['polished_text'])
                self.assertEqual(result['provider'], "MOCK")
                
                # Verify MOCK success log created
                self.assertTrue(LlmApiLog.objects.filter(provider="MOCK", status=LlmApiLog.Status.SUCCESS).exists())


from stories.services import ImageGeneratorService
from stories.models import Story, Scene
import tempfile
import os

class ImageGeneratorTestCase(TestCase):
    def setUp(self):
        self.story = Story.objects.create(prompt="Space explorer.")
        self.scene = Scene.objects.create(
            story=self.story,
            scene_number=1,
            prompt="Widescreen astronaut on the moon."
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_path = os.path.join(self.temp_dir.name, "test_img.jpg")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('requests.post')
    def test_huggingface_success(self, mock_post):
        """Verify HuggingFace executes successfully and writes seed and model details to the Scene."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_image_bytes"
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'HF_API_KEY': 'hf_test_key'}):
            result = ImageGeneratorService.generate_image_for_scene(self.scene, self.output_path)
            
            self.assertEqual(result['provider'], 'HUGGINGFACE')
            self.assertEqual(result['model'], 'FLUX.1-schnell')
            self.scene.refresh_from_db()
            self.assertEqual(self.scene.image_model, 'FLUX.1-schnell')
            self.assertTrue(self.scene.image_seed > 0)
            self.assertTrue(os.path.exists(self.output_path))
            with open(self.output_path, 'rb') as f:
                self.assertEqual(f.read(), b"fake_image_bytes")

    @patch('requests.post')
    @patch('requests.get')
    def test_huggingface_fail_fal_success_with_retry(self, mock_get, mock_post):
        """Verify fallback to Fal.ai after HF failure, with retry logic."""
        # First call is HF post (fail)
        hf_fail_response = MagicMock()
        hf_fail_response.raise_for_status.side_effect = Exception("HF Overloaded")
        
        # Second call is Fal post (succeed)
        fal_success_response = MagicMock()
        fal_success_response.status_code = 200
        fal_success_response.json.return_value = {'images': [{'url': 'http://fal.example.com/img.jpg'}]}
        
        mock_post.side_effect = [hf_fail_response, hf_fail_response, fal_success_response]
        
        # Mock get request to download image bytes
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.content = b"fal_image_bytes"
        mock_get.return_value = mock_get_response

        with patch.dict('os.environ', {'HF_API_KEY': 'hf_key', 'FAL_KEY': 'fal_key'}):
            result = ImageGeneratorService.generate_image_for_scene(self.scene, self.output_path)
            
            # Since HF fails on 1st try and 2nd retry, it cascades to FAL
            self.assertEqual(result['provider'], 'FAL_AI')
            self.assertEqual(result['model'], 'fal-ai/flux/schnell')
            self.scene.refresh_from_db()
            self.assertEqual(self.scene.image_model, 'fal-ai/flux/schnell')
            self.assertEqual(mock_post.call_count, 3)

    def test_pillow_mock_fallback_no_keys(self):
        """Verify Pillow gradient mock image creation runs when no keys are supplied."""
        with self.settings(HF_API_KEY='', FAL_KEY='', REPLICATE_API_TOKEN=''):
            with patch.dict('os.environ', {'HF_API_KEY': '', 'FAL_KEY': '', 'REPLICATE_API_TOKEN': ''}, clear=True):
                result = ImageGeneratorService.generate_image_for_scene(self.scene, self.output_path)
                
                self.assertEqual(result['provider'], 'MOCK')
                self.assertEqual(result['model'], 'MOCK_PILLOW')
                self.scene.refresh_from_db()
                self.assertEqual(self.scene.image_model, 'MOCK_PILLOW')
                self.assertTrue(os.path.exists(self.output_path))



from stories.services import SceneSplitterService

class SceneSplitterTestCase(TestCase):
    @patch('requests.post')
    def test_gemini_split_success(self, mock_post):
        """Verify Gemini executes successfully to split script and logs results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{'text': '```json\n[{"scene_number": 1, "title": "Intro", "description": "Start", "characters": "Astronaut", "environment": "Moon", "lighting": "Bright", "mood": "Excited", "camera_angle": "Wide", "image_prompt": "Beautiful space", "animation_prompt": "Zoom", "narration": "Hello space", "duration": 4.5}]\n```'}]
                }
            }]
        }
        mock_post.return_value = mock_response

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'gem_key'}):
            result = SceneSplitterService.split_story_into_scenes("Once upon a time.")
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['title'], "Intro")
            self.assertEqual(result[0]['duration'], 4.5)
            self.assertTrue(LlmApiLog.objects.filter(provider="GEMINI", status=LlmApiLog.Status.SUCCESS).exists())

    def test_mock_splitter_fallback_no_keys(self):
        """Verify mock splitter operates correctly and splits by paragraph when no API keys exist."""
        with self.settings(GEMINI_API_KEY='', GROQ_API_KEY='', OPENROUTER_API_KEY=''):
            with patch.dict('os.environ', {'GEMINI_API_KEY': '', 'GROQ_API_KEY': '', 'OPENROUTER_API_KEY': ''}, clear=True):
                script_text = "The astronaut floats in space.\nA giant spacecraft emerges."
                result = SceneSplitterService.split_story_into_scenes(script_text)
                
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0]['scene_number'], 1)
                self.assertEqual(result[0]['title'], "The Astronaut Floats")
                self.assertEqual(result[1]['title'], "A Giant Spacecraft")
                self.assertEqual(result[0]['characters'], "Cinematic space explorer")
                self.assertTrue(LlmApiLog.objects.filter(provider="MOCK", status=LlmApiLog.Status.SUCCESS).exists())


from history.models import PipelineRunLog
from pipeline.tasks import run_story_generation_pipeline
from ai.video_generation.manager import VideoGenerationManager

class PipelineTasksTestCase(TestCase):
    @patch('pipeline.tasks.generate_scene_video.delay')
    def test_pipeline_triggers_video_generation(self, mock_generate_video):
        """Verify that the celery pipeline starts, splits scenes, and schedules scene video generation."""
        story = Story.objects.create(
            title="Pipeline Test Story",
            prompt="First paragraph of the story.\nSecond paragraph of the story."
        )
        
        with self.settings(GEMINI_API_KEY='', GROQ_API_KEY='', OPENROUTER_API_KEY=''):
            with patch.dict('os.environ', {'GEMINI_API_KEY': '', 'GROQ_API_KEY': '', 'OPENROUTER_API_KEY': ''}, clear=True):
                result = run_story_generation_pipeline(story.id)
                
        story.refresh_from_db()
        self.assertEqual(story.status, Story.Status.PROCESSING)
        self.assertEqual(story.scenes.count(), 2)
        self.assertEqual(mock_generate_video.call_count, 2)
        
        # Verify logs
        logs = story.logs.all().order_by('started_at')
        steps = [log.step for log in logs]
        
        self.assertIn(PipelineRunLog.Step.STORY_INITIALIZATION, steps)
        self.assertIn(PipelineRunLog.Step.SCRIPT_GENERATION, steps)
        self.assertIn(PipelineRunLog.Step.DIRECT_VIDEO_GENERATION, steps)


class VideoGenerationTestCase(TestCase):
    def setUp(self):
        import tempfile
        self.story = Story.objects.create(
            title="Video Test Story",
            prompt="A test video generation prompt."
        )
        self.scene = Scene.objects.create(
            story=self.story,
            scene_number=1,
            prompt="Astronaut on Mars.",
            duration=4.0
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_path = os.path.join(self.temp_dir.name, "test_video.mp4")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('requests.post')
    @patch('requests.get')
    def test_successful_video_generation_fal(self, mock_get, mock_post):
        """Verify successful video generation using Fal.ai (primary provider)."""
        # Submission
        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"request_id": "fal_job_123"}
        mock_post.return_value = mock_submit

        # Status check
        mock_status = MagicMock()
        mock_status.status_code = 200
        mock_status.json.return_value = {"status": "COMPLETED"}
        
        # Results fetch
        mock_result = MagicMock()
        mock_result.status_code = 200
        mock_result.json.return_value = {"video": {"url": "http://example.com/video.mp4"}}
        
        # Video download
        mock_download = MagicMock()
        mock_download.status_code = 200
        mock_download.content = b"fake_video_bytes"
        
        mock_get.side_effect = [mock_status, mock_result, mock_download]

        with patch.dict('os.environ', {'FAL_API_KEY': 'test_fal_key'}):
            manager = VideoGenerationManager()
            # Isolate FalVideoProvider
            manager.providers = [manager.providers[0]]
            
            result = manager.generate_video_for_scene(self.scene, self.output_path)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["provider"], "FAL_AI")
            self.assertEqual(result["external_job_id"], "fal_job_123")

    @patch('requests.post')
    @patch('requests.get')
    def test_primary_fail_backup_success(self, mock_get, mock_post):
        """Verify fallback to Replicate when Fal.ai fails."""
        def post_side_effect(url, *args, **kwargs):
            if "fal.run" in url:
                resp = MagicMock()
                resp.status_code = 500
                resp.raise_for_status.side_effect = Exception("Fal API Error")
                return resp
            elif "replicate.com" in url:
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {"id": "rep_job_123"}
                return resp
            return MagicMock()
        
        mock_post.side_effect = post_side_effect
        
        # Replicate status check succeeds
        mock_status_rep = MagicMock()
        mock_status_rep.status_code = 200
        mock_status_rep.json.return_value = {"status": "succeeded", "output": ["http://example.com/video.mp4"]}
        
        # Download succeeds
        mock_download = MagicMock()
        mock_download.status_code = 200
        mock_download.content = b"fake_video_bytes"
        
        mock_get.side_effect = [mock_status_rep, mock_download]
        
        with patch.dict('os.environ', {'FAL_API_KEY': 'test_fal_key', 'REPLICATE_API_TOKEN': 'test_rep_token'}):
            manager = VideoGenerationManager()
            # Keep Fal and Replicate providers
            manager.providers = [manager.providers[0], manager.providers[1]]
            
            result = manager.generate_video_for_scene(self.scene, self.output_path)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["provider"], "REPLICATE")

    @patch('requests.post')
    @patch('requests.get')
    def test_all_apis_failure_mock_fallback(self, mock_get, mock_post):
        """Verify fallback to mock video creation when all API providers fail."""
        mock_post.side_effect = Exception("All APIs failed")
        
        # Mock FFmpeg / Pillow success
        with patch.object(VideoGenerationManager, '_generate_local_mock_video', return_value=True):
            with patch.dict('os.environ', {'FAL_API_KEY': 'a', 'REPLICATE_API_TOKEN': 'b', 'LUMA_API_KEY': 'c'}):
                manager = VideoGenerationManager()
                result = manager.generate_video_for_scene(self.scene, self.output_path)
                self.assertEqual(result["status"], "COMPLETED")
                self.assertEqual(result["provider"], "MOCK")

    @patch('requests.post')
    @patch('requests.get')
    def test_invalid_api_response(self, mock_get, mock_post):
        """Verify fail state on invalid JSON structure from API."""
        # Submission returns bad structure
        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"bad_key": "bad_val"}
        mock_post.return_value = mock_submit
        
        with patch.object(VideoGenerationManager, '_generate_local_mock_video', return_value=False):
            with patch.dict('os.environ', {'FAL_API_KEY': 'test_fal_key'}):
                manager = VideoGenerationManager()
                manager.providers = [manager.providers[0]]
                
                result = manager.generate_video_for_scene(self.scene, self.output_path)
                self.assertEqual(result["status"], "FAILED")

    @patch('requests.post')
    @patch('requests.get')
    def test_download_failure(self, mock_get, mock_post):
        """Verify fail state when video download returns error codes."""
        # Submission
        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"request_id": "fal_job_123"}
        mock_post.return_value = mock_submit

        # Status check
        mock_status = MagicMock()
        mock_status.status_code = 200
        mock_status.json.return_value = {"status": "COMPLETED"}
        
        # Results fetch
        mock_result = MagicMock()
        mock_result.status_code = 200
        mock_result.json.return_value = {"video": {"url": "http://example.com/video.mp4"}}
        
        # Download fails (returns status 404)
        mock_download = MagicMock()
        mock_download.status_code = 404
        mock_download.raise_for_status.side_effect = Exception("404 Not Found")
        
        mock_get.side_effect = [mock_status, mock_result, mock_download]

        with patch.object(VideoGenerationManager, '_generate_local_mock_video', return_value=False):
            with patch.dict('os.environ', {'FAL_API_KEY': 'test_fal_key'}):
                manager = VideoGenerationManager()
                manager.providers = [manager.providers[0]]
                
                result = manager.generate_video_for_scene(self.scene, self.output_path)
                self.assertEqual(result["status"], "FAILED")

    @patch('requests.post')
    @patch('requests.get')
    @patch('time.sleep', return_value=None) # skip sleep to speed up test
    def test_api_timeout(self, mock_sleep, mock_get, mock_post):
        """Verify timeout failure when polling stays generating indefinitely."""
        # Submission
        mock_submit = MagicMock()
        mock_submit.status_code = 200
        mock_submit.json.return_value = {"request_id": "fal_job_123"}
        mock_post.return_value = mock_submit

        # Status check keeps returning IN_PROGRESS
        mock_status = MagicMock()
        mock_status.status_code = 200
        mock_status.json.return_value = {"status": "IN_PROGRESS"}
        
        # Let's mock get status returning IN_PROGRESS 60 times
        mock_get.return_value = mock_status

        with patch.object(VideoGenerationManager, '_generate_local_mock_video', return_value=False):
            with patch.dict('os.environ', {'FAL_API_KEY': 'test_fal_key'}):
                manager = VideoGenerationManager()
                manager.providers = [manager.providers[0]]
                
                result = manager.generate_video_for_scene(self.scene, self.output_path)
                self.assertEqual(result["status"], "FAILED")
                self.assertIn("timed out", result["error"])




