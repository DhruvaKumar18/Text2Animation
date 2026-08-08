from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import StoryViewSet, SceneViewSet, PipelineRunLogViewSet

router = DefaultRouter()
router.register(r'stories', StoryViewSet, basename='story')
router.register(r'scenes', SceneViewSet, basename='scene')
router.register(r'logs', PipelineRunLogViewSet, basename='log')

urlpatterns = [
    path('', include(router.urls)),
]
