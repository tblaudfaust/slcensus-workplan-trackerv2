from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Administrator"
    PROJECT_OWNER = "PROJECT_OWNER", "Project Owner"
    WORKSTREAM_OWNER = "WORKSTREAM_OWNER", "Workstream Owner"
    CONTRIBUTOR = "CONTRIBUTOR", "Contributor"
    VIEWER = "VIEWER", "Viewer"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    phone = models.CharField(max_length=30, blank=True)
    receive_email_notifications = models.BooleanField(
        default=True,
        help_text="Turn off to stop receiving task/deadline/status notification emails.",
    )

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        full = self.get_full_name()
        return f"{full} ({self.username})" if full else self.username

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_project_owner_role(self):
        return self.role == Role.PROJECT_OWNER

    @property
    def is_workstream_owner_role(self):
        return self.role == Role.WORKSTREAM_OWNER

    @property
    def is_contributor_role(self):
        return self.role == Role.CONTRIBUTOR

    @property
    def is_viewer_role(self):
        return self.role == Role.VIEWER
