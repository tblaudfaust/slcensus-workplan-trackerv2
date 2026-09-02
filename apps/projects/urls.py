from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_create, name="create"),
    path("<int:pk>/", views.project_detail, name="detail"),
    path("<int:pk>/edit/", views.project_edit, name="edit"),
    path("<int:pk>/switch/", views.switch_project, name="switch"),
    path("<int:project_pk>/workstreams/new/", views.workstream_create, name="workstream_create"),
    path("workstreams/<int:pk>/", views.workstream_detail, name="workstream_detail"),
    path("workstreams/<int:pk>/edit/", views.workstream_edit, name="workstream_edit"),
]
