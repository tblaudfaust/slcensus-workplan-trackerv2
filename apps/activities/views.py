from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts import permissions
from apps.projects.models import Project, Workstream

from .forms import ActivityFilterForm, ActivityForm, CommentForm, RestrictedActivityForm
from .models import Activity, Comment, Status
from .services import record_changes, snapshot
from .signals import activity_changed, activity_created


def _active_project(request):
    project_id = request.session.get("active_project_id")
    if project_id:
        return Project.objects.filter(pk=project_id).first()
    return Project.objects.filter(is_active=True).order_by("name").first()


def _apply_filters(qs, form):
    if not form.is_valid():
        return qs
    data = form.cleaned_data
    if data.get("q"):
        qs = qs.filter(name__icontains=data["q"])
    if data.get("workstream"):
        qs = qs.filter(workstream=data["workstream"])
    if data.get("responsible"):
        qs = qs.filter(responsible=data["responsible"])
    if data.get("status"):
        qs = qs.filter(status=data["status"])
    if data.get("phase"):
        qs = qs.filter(phase__icontains=data["phase"])
    if data.get("start_from"):
        qs = qs.filter(start_date__gte=data["start_from"])
    if data.get("start_to"):
        qs = qs.filter(start_date__lte=data["start_to"])
    if data.get("end_from"):
        qs = qs.filter(end_date__gte=data["end_from"])
    if data.get("end_to"):
        qs = qs.filter(end_date__lte=data["end_to"])
    if data.get("unassigned_only"):
        qs = qs.filter(responsible__isnull=True, responsible_text="")
    if data.get("overdue_only"):
        today = timezone.localdate()
        qs = qs.filter(end_date__lt=today).exclude(status="COMPLETED")
    return qs


@login_required
def activity_list(request):
    project = _active_project(request)
    if project is None:
        messages.info(request, "Create a project before adding activities.")
        return redirect("projects:list")

    qs = Activity.objects.filter(project=project).select_related("workstream", "responsible")
    form = ActivityFilterForm(request.GET or None, project=project)
    qs = _apply_filters(qs, form)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)
    querystring_without_page = (querystring.urlencode() + "&") if querystring else ""

    return render(
        request,
        "activities/activity_list.html",
        {
            "project": project,
            "form": form,
            "page": page,
            "total_count": qs.count(),
            "querystring_without_page": querystring_without_page,
        },
    )


@login_required
def activity_detail(request, pk):
    activity = get_object_or_404(
        Activity.objects.select_related("project", "workstream", "responsible"), pk=pk
    )
    can_edit = permissions.can_edit_activity(request.user, activity)

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.activity = activity
            comment.user = request.user
            comment.save()
            messages.success(request, "Comment added.")
            return redirect("activities:detail", activity.pk)
    else:
        comment_form = CommentForm()

    return render(
        request,
        "activities/activity_detail.html",
        {
            "activity": activity,
            "can_edit": can_edit,
            "can_delete": permissions.can_delete_activity(request.user, activity),
            "can_validate": permissions.can_validate_completion(request.user, activity),
            "comment_form": comment_form,
            "history": activity.history.select_related("changed_by")[:50],
            "comments": activity.comments.select_related("user"),
        },
    )


@login_required
def activity_create(request):
    project = _active_project(request)
    if project is None:
        messages.info(request, "Create a project before adding activities.")
        return redirect("projects:list")
    if not (
        permissions.is_admin(request.user)
        or permissions.can_manage_project(request.user, project)
        or permissions.is_workstream_owner(request.user)
    ):
        messages.error(request, "You don't have permission to create activities.")
        return redirect("activities:list")

    if request.method == "POST":
        form = ActivityForm(request.POST, project=project)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.project = project
            activity.save()
            activity_created.send(sender=Activity, activity=activity, changed_by=request.user, source="MANUAL")
            messages.success(request, "Activity created.")
            return redirect("activities:detail", activity.pk)
    else:
        initial = {}
        ws_id = request.GET.get("workstream")
        if ws_id:
            initial["workstream"] = ws_id
        form = ActivityForm(project=project, initial=initial)

    return render(request, "activities/activity_form.html", {"form": form, "is_create": True, "project": project})


@login_required
def activity_edit(request, pk):
    activity = get_object_or_404(Activity.objects.select_related("project"), pk=pk)
    if not permissions.can_edit_activity(request.user, activity):
        messages.error(request, "You don't have permission to edit this activity.")
        return redirect("activities:detail", activity.pk)

    form_class = ActivityForm if permissions.is_admin(request.user) or permissions.is_project_owner(
        request.user
    ) or permissions.is_workstream_owner(request.user) else RestrictedActivityForm

    if request.method == "POST":
        before = snapshot(activity)
        form = form_class(request.POST, instance=activity, project=activity.project)
        if form.is_valid():
            form.save()
            changed_fields = record_changes(activity, before, changed_by=request.user, source="MANUAL")
            if changed_fields:
                activity_changed.send(
                    sender=Activity,
                    activity=activity,
                    changed_fields=changed_fields,
                    changed_by=request.user,
                    source="MANUAL",
                )
            messages.success(request, "Activity updated.")
            return redirect("activities:detail", activity.pk)
    else:
        form = form_class(instance=activity, project=activity.project)

    return render(
        request,
        "activities/activity_form.html",
        {"form": form, "is_create": False, "activity": activity, "project": activity.project},
    )


@login_required
def activity_validate(request, pk):
    activity = get_object_or_404(Activity.objects.select_related("project", "workstream"), pk=pk)
    if not permissions.can_validate_completion(request.user, activity):
        messages.error(request, "Only the workstream's lead/backup lead (or above) can validate a completion.")
        return redirect("activities:detail", activity.pk)
    if activity.status != Status.PENDING_VALIDATION:
        messages.error(request, "Only activities marked Pending Validation can be validated.")
        return redirect("activities:detail", activity.pk)

    if request.method == "POST":
        before = snapshot(activity)
        activity.status = Status.COMPLETED
        activity.progress_percent = 100
        activity.validated_by = request.user
        activity.validated_at = timezone.now()
        activity.save()
        changed_fields = record_changes(activity, before, changed_by=request.user, source="MANUAL")
        if changed_fields:
            activity_changed.send(
                sender=Activity,
                activity=activity,
                changed_fields=changed_fields,
                changed_by=request.user,
                source="MANUAL",
            )
        _notify_completion_validated(activity)
        messages.success(request, f"'{activity.name}' validated and marked Completed.")
    return redirect("activities:detail", activity.pk)


@login_required
def activity_send_back(request, pk):
    activity = get_object_or_404(Activity.objects.select_related("project", "workstream"), pk=pk)
    if not permissions.can_validate_completion(request.user, activity):
        messages.error(request, "Only the workstream's lead/backup lead (or above) can send this back.")
        return redirect("activities:detail", activity.pk)
    if activity.status != Status.PENDING_VALIDATION:
        messages.error(request, "Only activities marked Pending Validation can be sent back.")
        return redirect("activities:detail", activity.pk)

    if request.method == "POST":
        before = snapshot(activity)
        activity.status = Status.ONGOING
        activity.save()
        changed_fields = record_changes(activity, before, changed_by=request.user, source="MANUAL")
        if changed_fields:
            activity_changed.send(
                sender=Activity,
                activity=activity,
                changed_fields=changed_fields,
                changed_by=request.user,
                source="MANUAL",
            )
        reason = request.POST.get("reason", "").strip()
        if reason:
            Comment.objects.create(activity=activity, user=request.user, body=f"Sent back for more work: {reason}")
        messages.success(request, f"'{activity.name}' sent back to Ongoing.")
    return redirect("activities:detail", activity.pk)


def _notify_completion_validated(activity):
    from apps.notifications.emailing import eligible_recipients, rule_enabled, send_notification
    from apps.notifications.models import RuleType

    if not rule_enabled(RuleType.COMPLETION_VALIDATED):
        return
    owner = activity.project.owner
    recipients = eligible_recipients(owner)
    send_notification(
        rule_type=RuleType.COMPLETION_VALIDATED,
        template="completion_validated",
        subject=f"[Census Tracker] Completion validated: {activity.name}",
        context={
            "activity": activity,
            "recipient_name": owner.get_full_name() or owner.username,
            "validated_by": activity.validated_by,
            "validated_at": activity.validated_at,
        },
        recipients=recipients,
        activity=activity,
    )


@login_required
def activity_delete(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    if not permissions.can_delete_activity(request.user, activity):
        messages.error(request, "You don't have permission to delete this activity.")
        return redirect("activities:detail", activity.pk)
    if request.method == "POST":
        name = activity.name
        activity.delete()
        messages.success(request, f"Activity '{name}' deleted.")
        return redirect("activities:list")
    return render(request, "activities/activity_confirm_delete.html", {"activity": activity})
