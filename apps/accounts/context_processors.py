from . import permissions


def role_flags(request):
    """Cheap booleans for template nav-item gating. Views still enforce the
    real permission checks in apps.accounts.permissions -- these are only
    for hiding links a user couldn't act on anyway."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {
        "perms_is_admin": permissions.is_admin(user),
        "perms_can_upload": permissions.can_upload_workplans(user),
    }
