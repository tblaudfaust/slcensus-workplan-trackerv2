from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.activities.forms import ActivityFilterForm
from apps.activities.models import Activity, Status
from apps.activities.views import _apply_filters
from apps.projects.models import Project


def _active_project(request):
    project_id = request.session.get("active_project_id")
    if project_id:
        return Project.objects.filter(pk=project_id).first()
    return Project.objects.filter(is_active=True).order_by("name").first()


def _filtered_queryset(request, project):
    qs = Activity.objects.filter(project=project).select_related("workstream", "responsible")
    form = ActivityFilterForm(request.GET or None, project=project)
    return _apply_filters(qs, form), form


@login_required
def home(request):
    project = _active_project(request)
    if project is None:
        messages.info(request, "Create a project to get started.")
        return redirect("projects:list")

    qs, form = _filtered_queryset(request, project)
    qs = list(qs)  # small dataset per project; avoids N+1 re-querying below
    kpis = _kpis_from_list(qs)
    workstream_rows = _workstream_performance_from_list(project, qs)

    upcoming = sorted(
        [a for a in qs if a.end_date and a.status != Status.COMPLETED and a.end_date >= timezone.localdate()],
        key=lambda a: a.end_date,
    )[:10]
    overdue_list = sorted(
        [a for a in qs if a.is_overdue], key=lambda a: a.end_date
    )[:10]
    unassigned_list = [a for a in qs if not a.has_owner][:10]

    return render(
        request,
        "dashboard/home.html",
        {
            "project": project,
            "form": form,
            "kpis": kpis,
            "workstream_rows": workstream_rows,
            "upcoming": upcoming,
            "overdue_list": overdue_list,
            "unassigned_list": unassigned_list,
        },
    )


def _kpis_from_list(activities):
    today = timezone.localdate()
    total = len(activities)
    status_counts = {s.value: 0 for s in Status}
    for a in activities:
        status_counts[a.status] += 1
    overdue = sum(1 for a in activities if a.is_overdue)
    unassigned = sum(1 for a in activities if not a.has_owner)
    due_today = sum(1 for a in activities if a.end_date == today and a.status != Status.COMPLETED)
    week_end = today + timezone.timedelta(days=6)
    due_this_week = sum(
        1 for a in activities if a.end_date and today <= a.end_date <= week_end and a.status != Status.COMPLETED
    )

    def due_within(days):
        cutoff = today + timezone.timedelta(days=days)
        return sum(
            1 for a in activities if a.end_date and today <= a.end_date <= cutoff and a.status != Status.COMPLETED
        )

    milestones = [a for a in activities if a.is_milestone]
    readiness = round((status_counts[Status.COMPLETED] / total) * 100) if total else 0

    return {
        "total": total,
        "status_counts": status_counts,
        "overdue": overdue,
        "unassigned": unassigned,
        "due_today": due_today,
        "due_this_week": due_this_week,
        "due_7": due_within(7),
        "due_14": due_within(14),
        "due_30": due_within(30),
        "milestones": len(milestones),
        "milestones_completed": sum(1 for a in milestones if a.status == Status.COMPLETED),
        "readiness": readiness,
    }


def _workstream_performance_from_list(project, activities):
    from collections import defaultdict

    totals, completed, overdue = defaultdict(int), defaultdict(int), defaultdict(int)
    for a in activities:
        totals[a.workstream_id] += 1
        if a.status == Status.COMPLETED:
            completed[a.workstream_id] += 1
        if a.is_overdue:
            overdue[a.workstream_id] += 1

    rows = []
    for ws in project.workstreams.all():
        total = totals.get(ws.id, 0)
        done = completed.get(ws.id, 0)
        rows.append(
            {
                "workstream": ws,
                "total": total,
                "completed": done,
                "overdue": overdue.get(ws.id, 0),
                "percent": round((done / total) * 100) if total else 0,
            }
        )
    return rows


@login_required
def chart_data(request):
    project = _active_project(request)
    if project is None:
        return JsonResponse({"status_labels": [], "status_values": [], "workstream_labels": [], "workstream_values": []})
    qs, _ = _filtered_queryset(request, project)
    activities = list(qs)
    kpis = _kpis_from_list(activities)
    ws_rows = _workstream_performance_from_list(project, activities)

    return JsonResponse(
        {
            "status_labels": [Status(s).label for s in kpis["status_counts"].keys()],
            "status_values": list(kpis["status_counts"].values()),
            "workstream_labels": [row["workstream"].name for row in ws_rows],
            "workstream_values": [row["percent"] for row in ws_rows],
        }
    )


@login_required
def gantt_data(request):
    project = _active_project(request)
    if project is None:
        return JsonResponse([], safe=False)
    qs, _ = _filtered_queryset(request, project)
    tasks = []
    for a in qs.exclude(start_date__isnull=True).exclude(end_date__isnull=True).order_by("start_date")[:150]:
        css_class = "gantt-overdue" if a.is_overdue else f"gantt-{a.status.lower()}"
        tasks.append(
            {
                "id": str(a.id),
                "name": f"{a.name} ({a.workstream.name})",
                "start": a.start_date.isoformat(),
                "end": a.end_date.isoformat(),
                "progress": a.progress_percent,
                "custom_class": css_class,
                "url": a.get_absolute_url(),
            }
        )
    return JsonResponse(tasks, safe=False)
