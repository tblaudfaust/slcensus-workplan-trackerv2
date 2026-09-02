from django.urls import path

from . import views

app_name = "activities"

urlpatterns = [
    path("", views.activity_list, name="list"),
    path("new/", views.activity_create, name="create"),
    path("<int:pk>/", views.activity_detail, name="detail"),
    path("<int:pk>/edit/", views.activity_edit, name="edit"),
    path("<int:pk>/delete/", views.activity_delete, name="delete"),
]
