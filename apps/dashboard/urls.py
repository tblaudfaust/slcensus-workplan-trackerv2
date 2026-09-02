from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("data/charts.json", views.chart_data, name="chart_data"),
    path("data/gantt.json", views.gantt_data, name="gantt_data"),
]
