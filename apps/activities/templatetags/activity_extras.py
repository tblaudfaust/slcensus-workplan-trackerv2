from django import template

register = template.Library()


@register.inclusion_tag("activities/_status_badge.html")
def status_badge(activity):
    css_class = "status-OVERDUE" if activity.is_overdue else f"status-{activity.status}"
    label = "Overdue" if activity.is_overdue else activity.get_status_display()
    return {"css_class": css_class, "label": label}


@register.filter
def percent_of(count, total):
    if not total:
        return 0
    return round((count / total) * 100)
