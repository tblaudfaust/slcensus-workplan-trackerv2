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
    from apps.activities.models import Status

    workstream = get_object_or_404(
        Workstream.objects.select_related("project", "lead", "backup_lead"), pk=pk
    )
    activities = list(workstream.activities.select_related("responsible"))
    total = len(activities)
    completed = sum(1 for a in activities if a.status == Status.COMPLETED)
    overdue = sum(1 for a in activities if a.is_overdue)
    unassigned = sum(1 for a in activities if not a.has_owner)

    return render(
        request,
        "projects/workstream_detail.html",
        {
            "workstream": workstream,
            "activities": activities,
            "stats": {
                "total": total,
                "completed": completed,
                "overdue": overdue,
                "unassigned": unassigned,
                "percent": round((completed / total) * 100) if total else 0,
            },
            "can_alert": permissions.can_validate_completion(request.user, _WorkstreamActivityStandin(workstream)),
        },
    )


class _WorkstreamActivityStandin:
    """can_validate_completion is written to check permissions against an
    Activity (it needs .project and .workstream_id); the alert button's
    permission check is really "does this user have authority over this
    workstream" with no specific activity involved, so this adapts a bare
    Workstream to that same interface rather than duplicating the role
    logic in a second function."""

    def __init__(self, workstream):
        self.project = workstream.project
        self.workstream_id = workstream.id


@login_required
def workstream_send_alert(request, pk):
    workstream = get_object_or_404(
        Workstream.objects.select_related("project", "project__owner", "lead", "backup_lead"), pk=pk
    )
    if not permissions.can_validate_completion(request.user, _WorkstreamActivityStandin(workstream)):
        messages.error(request, "You don't have permission to send an alert for this workstream.")
        return redirect("projects:workstream_detail", workstream.pk)

    if request.method == "POST":
        from apps.notifications.emailing import eligible_recipients, send_notification
        from apps.notifications.models import RuleType

        from apps.activities.models import Status

        activities = list(workstream.activities.all())
        total = len(activities)
        completed = sum(1 for a in activities if a.status == Status.COMPLETED)
        overdue = sum(1 for a in activities if a.is_overdue)
        percent = round((completed / total) * 100) if total else 0

        recipients = eligible_recipients(workstream.lead, workstream.backup_lead, workstream.project.owner)
        message = request.POST.get("message", "").strip()
        sent = send_notification(
            rule_type=RuleType.MANUAL_ALERT,
            template="workstream_status_alert",
            subject=f"[Census Tracker] Status alert: {workstream.name}",
            context={
                "recipient_name": "team",
                "workstream": workstream,
                "triggered_by": request.user.get_full_name() or request.user.username,
                "total": total,
                "completed": completed,
                "overdue": overdue,
                "percent": percent,
                "message": message,
            },
            recipients=recipients,
            workstream=workstream,
        )
        if sent:
            messages.success(request, f"Alert sent to {sent} recipient(s).")
        else:
            messages.warning(request, "No recipients have a usable email on file (lead, backup lead, or project owner).")
    return redirect("projects:workstream_detail", workstream.pk)


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
