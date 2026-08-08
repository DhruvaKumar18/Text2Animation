from django.shortcuts import render, get_object_or_404
from stories.models import Story

def dashboard_index(request):
    """
    Renders the dashboard main list page showing all stories and the prompt form.
    """
    stories = Story.objects.all().order_by('-created_at')
    return render(request, 'dashboard/index.html', {'stories': stories})

def dashboard_detail(request, pk):
    """
    Renders the detail page for a specific story containing the video player and scene log lists.
    """
    story = get_object_or_404(Story, pk=pk)
    return render(request, 'dashboard/detail.html', {'story': story})

def dashboard_upload(request):
    """
    Renders the story upload page with drag & drop document parser and text preview.
    """
    return render(request, 'dashboard/upload.html')

