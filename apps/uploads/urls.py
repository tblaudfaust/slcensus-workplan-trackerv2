from django.urls import path

from . import views

app_name = "uploads"

urlpatterns = [
    path("", views.upload_start, name="start"),
    path("preview/", views.upload_preview, name="preview"),
    path("history/", views.upload_history, name="history"),
    path("history/<int:pk>/", views.upload_batch_detail, name="batch_detail"),
]
