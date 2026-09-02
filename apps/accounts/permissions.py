"""Role-based access helpers shared across apps.

Kept as plain functions (not a permissions backend) so every view makes an
explicit, readable check rather than relying on hidden template-only gating.
"""

from .models import Role


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == Role.ADMIN)


def is_project_owner(user):
    return user.is_authenticated and user.role == Role.PROJECT_OWNER


def is_workstream_owner(user):
    return user.is_authenticated and user.role == Role.WORKSTREAM_OWNER


def is_contributor(user):
    return user.is_authenticated and user.role == Role.CONTRIBUTOR


def can_manage_users(user):
    return is_admin(user)


def can_manage_notification_settings(user):
    return is_admin(user)


def can_upload_workplans(user):
    """Admins, project owners, and workstream owners may import workbooks."""
    return is_admin(user) or is_project_owner(user) or is_workstream_owner(user)


def can_manage_project(user, project):
    """Create/edit workstreams, assign owners, edit any activity in the project."""
    if is_admin(user):
        return True
    if is_project_owner(user):
        return project.owner_id == user.id
    return False


def owned_workstream_ids(user):
    return set(user.led_workstreams.values_list("id", flat=True)) | set(
        user.workstreams.values_list("id", flat=True)
    )


def can_edit_activity(user, activity):
    """Admin/Project Owner (of the project) edit anything; Workstream Owner
    edits within their workstream(s); Contributor edits only activities they
    are responsible for (status/progress/comments); Viewer never edits."""
    if not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    if is_project_owner(user):
        return activity.project.owner_id == user.id
    if is_workstream_owner(user):
        return activity.workstream_id in owned_workstream_ids(user)
    if is_contributor(user):
        return activity.responsible_id == user.id
    return False


def can_delete_activity(user, activity):
    """Deleting activity records is reserved for admins and the owning
    project owner -- contributors/workstream owners can edit status but
    should not be able to erase history."""
    if not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    if is_project_owner(user):
        return activity.project.owner_id == user.id
    return False


def can_view_project(user, project):
    """Every authenticated role can view; kept as a function (rather than
    "any authenticated user") so a future project-level restriction (e.g.
    private census projects) only needs to change this one place."""
    return user.is_authenticated


def visible_workstream_queryset(user, project):
    """Workstreams a Workstream Owner/Contributor should see narrowed to
    their own by default; Admin/Project Owner/Viewer see all of a project's
    workstreams."""
    qs = project.workstreams.all()
    if is_admin(user) or is_project_owner(user) or user.is_viewer_role:
        return qs
    if is_workstream_owner(user):
        return qs.filter(id__in=owned_workstream_ids(user))
    return qs
