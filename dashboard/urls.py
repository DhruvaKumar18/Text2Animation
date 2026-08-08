from django.urls import path
from dashboard.views import dashboard_index, dashboard_detail, dashboard_upload

app_name = 'dashboard'

urlpatterns = [
    path('', dashboard_index, name='index'),
    path('story/new/', dashboard_upload, name='upload'),
    path('story/<int:pk>/', dashboard_detail, name='detail'),
]
