import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status
from apps.projects.models import Project, Workstream

WORKSTREAM_NAMES = [
    "General",
    "GIS",
    "Human Resources",
    "Logistics/Data Science",
    "CCIT",
    "End-to-End Systems",
    "Publicity",
    "Field Operations",
    "Data Science",
]

ACTIVITY_TEMPLATES = [
    ("Finalize enumeration area boundaries", "GIS shapefiles reviewed and signed off", 30, True),
    ("Recruit district-level field supervisors", "Signed supervisor contracts", 21, False),
    ("Procure tablets for CAPI data collection", "Delivered and tested devices", 45, True),
    ("Develop CAPI questionnaire application", "Tested application build", 60, True),
    ("Conduct census publicity campaign - phase 1", "Media coverage report", 40, False),
    ("Train national trainers", "Training completion certificates", 14, False),
    ("Pilot census enumeration", "Pilot report with lessons learned", 20, True),
    ("Set up data processing centre", "Operational processing centre", 35, False),
    ("Print questionnaires and field manuals", "Delivered print stock", 25, False),
    ("Establish helpdesk and CCIT support desk", "Helpdesk go-live", 18, False),
]


class Command(BaseCommand):
    help = "Creates demo users, a sample project, its workstreams, and sample activities for local testing."

    def handle(self, *args, **options):
        admin = self._get_or_create_user("admin", Role.ADMIN, "Ada", "Minister", is_superuser=True, is_staff=True)
        owner = self._get_or_create_user("pmoore", Role.PROJECT_OWNER, "Patricia", "Moore")
        ws_owner = self._get_or_create_user("wskamara", Role.WORKSTREAM_OWNER, "Wusu", "Kamara")
        contributor = self._get_or_create_user("ckoroma", Role.CONTRIBUTOR, "Christiana", "Koroma")
        self._get_or_create_user("vsesay", Role.VIEWER, "Victor", "Sesay")

        project, _ = Project.objects.get_or_create(
            name="2026 Population and Housing Census",
            defaults={
                "description": "National census workplan tracked across all technical workstreams.",
                "census_year": 2026,
                "owner": owner,
            },
        )

        workstreams = {}
        for i, name in enumerate(WORKSTREAM_NAMES):
            lead = ws_owner if i == 0 else None
            ws, _ = Workstream.objects.get_or_create(project=project, name=name, defaults={"lead": lead})
            workstreams[name] = ws

        if Activity.objects.filter(project=project).exists():
            self.stdout.write("Demo activities already exist; skipping activity creation.")
        else:
            today = timezone.localdate()
            random.seed(42)
            for ws_name, ws in workstreams.items():
                for name_template, deliverable, base_days, is_milestone in ACTIVITY_TEMPLATES:
                    offset = random.randint(-40, 60)
                    end = today + timedelta(days=offset)
                    start = end - timedelta(days=base_days)
                    status, progress = self._status_for_offset(offset)
                    Activity.objects.create(
                        project=project,
                        workstream=ws,
                        name=f"{name_template} — {ws_name}",
                        start_date=start,
                        end_date=end,
                        dependency="Approved budget and prior-phase sign-off",
                        deliverable=deliverable,
                        responsible=contributor if random.random() > 0.3 else None,
                        responsible_text="" if random.random() > 0.3 else "External Consultant",
                        status=status,
                        progress_percent=progress,
                        phase="Pre-enumeration",
                        is_milestone=is_milestone,
                    )
            self.stdout.write(self.style.SUCCESS("Demo activities created."))

        self.stdout.write(self.style.SUCCESS("Seed complete. Login as admin/admin12345, pmoore/admin12345, etc."))

    def _status_for_offset(self, offset_days):
        if offset_days < -5:
            return random.choice([Status.DELAYED, Status.AT_RISK]), random.randint(20, 70)
        if offset_days < 0:
            return Status.ONGOING, random.randint(60, 95)
        if offset_days < 10:
            return random.choice([Status.ONGOING, Status.AT_RISK]), random.randint(30, 80)
        if offset_days > 45:
            return Status.NOT_STARTED, 0
        return random.choice([Status.ONGOING, Status.COMPLETED, Status.NOT_STARTED]), random.choice([0, 25, 50, 75, 100])

    def _get_or_create_user(self, username, role, first_name, last_name, is_superuser=False, is_staff=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{username}@example.org",
                "role": role,
                "is_superuser": is_superuser,
                "is_staff": is_staff or is_superuser,
            },
        )
        if created:
            user.set_password("admin12345")
            user.save()
        return user
