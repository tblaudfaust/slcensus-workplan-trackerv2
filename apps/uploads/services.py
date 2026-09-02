from django.db import transaction

from apps.activities.models import Activity
from apps.activities.services import record_changes, snapshot
from apps.activities.signals import activity_changed, activity_created
from apps.projects.models import Workstream

from .models import UploadBatch
from .parsing import parse_sheet


@transaction.atomic
def commit_upload(*, project, workstream_override, sheets, mapping, uploaded_by, file_name):
    """Parses every sheet with its (possibly user-corrected) column mapping,
    then creates/updates Activity rows. Matching is by (workstream, name)
    via Activity.build_row_key -- an existing activity in the same
    workstream with the same name is treated as the same activity and
    updated in place (with per-field history logging); everything else is
    created new."""

    batch = UploadBatch(
        file_name=file_name,
        uploaded_by=uploaded_by,
        project=project,
        workstream=workstream_override,
        sheet_names=list(sheets.keys()),
        column_mapping=mapping,
    )

    errors = []
    created = updated = skipped = total = 0

    for sheet_name, df in sheets.items():
        sheet_mapping = mapping.get(sheet_name, {})
        default_ws_name = workstream_override.name if workstream_override else sheet_name
        parsed_rows = parse_sheet(df, sheet_mapping, default_workstream_name=default_ws_name)

        for row in parsed_rows:
            total += 1
            if not row.is_valid:
                skipped += 1
                errors.append({"sheet": sheet_name, "row": row.row_number, "errors": row.errors})
                continue

            data = row.data
            workstream = workstream_override or _get_or_create_workstream(project, data["workstream_name"])
            row_key = Activity.build_row_key(workstream.id, data["name"])

            existing = Activity.objects.filter(project=project, source_row_key=row_key).first()
            responsible_user = _match_responsible(data["responsible_text"])

            if existing:
                before = snapshot(existing)
                existing.workstream = workstream
                existing.name = data["name"]
                if data["start_date"] is not None:
                    existing.start_date = data["start_date"]
                if data["end_date"] is not None:
                    existing.end_date = data["end_date"]
                if data["duration_days"] is not None:
                    existing.duration_days = data["duration_days"]
                existing.dependency = data["dependency"] or existing.dependency
                existing.deliverable = data["deliverable"] or existing.deliverable
                if responsible_user:
                    existing.responsible = responsible_user
                existing.responsible_text = data["responsible_text"] or existing.responsible_text
                existing.status = data["status"]
                if data["progress_percent"] is not None:
                    existing.progress_percent = data["progress_percent"]
                existing.phase = data["phase"] or existing.phase
                existing.remarks = data["remarks"] or existing.remarks
                existing.save()
                changed_fields = record_changes(existing, before, changed_by=uploaded_by, source="UPLOAD")
                if changed_fields:
                    activity_changed.send(
                        sender=Activity,
                        activity=existing,
                        changed_fields=changed_fields,
                        changed_by=uploaded_by,
                        source="UPLOAD",
                    )
                    updated += 1
            else:
                activity = Activity.objects.create(
                    project=project,
                    workstream=workstream,
                    name=data["name"],
                    start_date=data["start_date"],
                    end_date=data["end_date"],
                    duration_days=data["duration_days"],
                    dependency=data["dependency"],
                    deliverable=data["deliverable"],
                    responsible=responsible_user,
                    responsible_text=data["responsible_text"],
                    status=data["status"],
                    progress_percent=data["progress_percent"] or 0,
                    phase=data["phase"],
                    remarks=data["remarks"],
                )
                activity_created.send(sender=Activity, activity=activity, changed_by=uploaded_by, source="UPLOAD")
                created += 1

    batch.rows_total = total
    batch.rows_created = created
    batch.rows_updated = updated
    batch.rows_skipped = skipped
    batch.errors = errors
    batch.save()
    return batch


def _get_or_create_workstream(project, name):
    name = (name or "General").strip() or "General"
    workstream = Workstream.objects.filter(project=project, name__iexact=name).first()
    if workstream:
        return workstream
    return Workstream.objects.create(project=project, name=name)


def _match_responsible(text):
    if not text:
        return None
    from apps.accounts.models import User

    text = text.strip()
    return (
        User.objects.filter(email__iexact=text).first()
        or User.objects.filter(username__iexact=text).first()
        or _match_by_full_name(text)
    )


def _match_by_full_name(text):
    from apps.accounts.models import User

    for user in User.objects.filter(is_active=True):
        full = user.get_full_name()
        if full and full.strip().lower() == text.lower():
            return user
    return None
