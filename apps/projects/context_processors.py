from .models import Project


def active_project(request):
    """Makes the currently selected Project (and the full list, for the
    switcher in the nav bar) available to every template. The active
    project is remembered per-session so multi-project deployments don't
    need it threaded through every URL."""
    if not request.user.is_authenticated:
        return {}

    projects = list(Project.objects.filter(is_active=True).order_by("name"))
    active_id = request.session.get("active_project_id")
    active = next((p for p in projects if p.id == active_id), None)
    if active is None and projects:
        active = projects[0]
        request.session["active_project_id"] = active.id

    return {"nav_projects": projects, "active_project": active}
