from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts import permissions

from .forms import ProjectForm, WorkstreamForm
from .models import Project, Workstream


@login_required
def project_list(request):
    projects = Project.objects.select_related("owner").prefetch_related("workstreams")
    return render(request, "projects/project_list.html", {"projects": projects})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project.objects.select_related("owner"), pk=pk)
    workstreams = project.workstreams.select_related("lead").prefetch_related("activities")
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "workstreams": workstreams,
            "can_manage": permissions.can_manage_project(request.user, project),
        },
    )


@login_required
@user_passes_test(permissions.is_admin)
def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            messages.success(request, f"Project '{project.name}' created.")
            return redirect("projects:detail", project.pk)
    else:
        form = ProjectForm()
    return render(request, "projects/project_form.html", {"form": form, "is_create": True})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not permissions.can_manage_project(request.user, project):
        messages.error(request, "You don't have permission to edit this project.")
        return redirect("projects:detail", project.pk)
    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, "Project updated.")
            return redirect("projects:detail", project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, "projects/project_form.html", {"form": form, "is_create": False, "project": project})


@login_required
def workstream_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not permissions.can_manage_project(request.user, project):
        messages.error(request, "You don't have permission to add workstreams to this project.")
        return redirect("projects:detail", project.pk)
    if request.method == "POST":
        form = WorkstreamForm(request.POST)
        if form.is_valid():
            workstream = form.save(commit=False)
            workstream.project = project
            workstream.save()
            form.save_m2m()
            messages.success(request, f"Workstream '{workstream.name}' added.")
            return redirect("projects:detail", project.pk)
    else:
        form = WorkstreamForm()
    return render(request, "projects/workstream_form.html", {"form": form, "project": project, "is_create": True})


@login_required
def workstream_detail(request, pk):
    workstream = get_object_or_404(Workstream.objects.select_related("project", "lead"), pk=pk)
    activities = workstream.activities.select_related("responsible")
    return render(request, "projects/workstream_detail.html", {"workstream": workstream, "activities": activities})


@login_required
def workstream_edit(request, pk):
    workstream = get_object_or_404(Workstream.objects.select_related("project"), pk=pk)
    if not permissions.can_manage_project(request.user, workstream.project):
        messages.error(request, "You don't have permission to edit this workstream.")
        return redirect("projects:workstream_detail", workstream.pk)
    if request.method == "POST":
        form = WorkstreamForm(request.POST, instance=workstream)
        if form.is_valid():
            form.save()
            messages.success(request, "Workstream updated.")
            return redirect("projects:workstream_detail", workstream.pk)
    else:
        form = WorkstreamForm(instance=workstream)
    return render(
        request,
        "projects/workstream_form.html",
        {"form": form, "project": workstream.project, "is_create": False, "workstream": workstream},
    )


@login_required
def switch_project(request, pk):
    project = get_object_or_404(Project, pk=pk, is_active=True)
    request.session["active_project_id"] = project.id
    next_url = request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return HttpResponseRedirect(next_url)
    return redirect("dashboard:home")
