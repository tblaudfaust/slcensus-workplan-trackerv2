import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts import permissions
from apps.projects.models import Workstream

from .forms import UploadForm
from .models import UploadBatch
from .parsing import FIELDS, match_columns, parse_sheet, read_uploaded_file
from .services import commit_upload

SESSION_KEY = "pending_upload"


def _require_upload_permission(user):
    return permissions.can_upload_workplans(user)


@login_required
@user_passes_test(_require_upload_permission)
def upload_start(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            project = form.cleaned_data["project"]
            workstream = form.cleaned_data.get("workstream")

            settings.UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            tmp_dir = settings.UPLOAD_TMP_DIR / token
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / uploaded.name
            with open(tmp_path, "wb") as f:
                for chunk in uploaded.chunks():
                    f.write(chunk)

            try:
                sheets = read_uploaded_file(open(tmp_path, "rb"), uploaded.name)
            except Exception as exc:
                messages.error(request, f"Could not read this file: {exc}")
                return render(request, "uploads/upload_form.html", {"form": form})

            mapping = {}
            for sheet_name, df in sheets.items():
                field_map, _unmatched = match_columns(list(df.columns))
                mapping[sheet_name] = field_map

            request.session[SESSION_KEY] = {
                "token": token,
                "tmp_path": str(tmp_path),
                "file_name": uploaded.name,
                "project_id": project.id,
                "workstream_id": workstream.id if workstream else None,
                "mapping": mapping,
            }
            return redirect("uploads:preview")
    else:
        form = UploadForm()
    return render(request, "uploads/upload_form.html", {"form": form})


def _load_pending(request):
    pending = request.session.get(SESSION_KEY)
    if not pending or not Path(pending["tmp_path"]).exists():
        return None
    return pending


@login_required
@user_passes_test(_require_upload_permission)
def upload_preview(request):
    pending = _load_pending(request)
    if not pending:
        messages.error(request, "No upload in progress. Please upload a file to begin.")
        return redirect("uploads:start")

    from apps.projects.models import Project

    project = get_object_or_404(Project, pk=pending["project_id"])
    workstream = Workstream.objects.filter(pk=pending["workstream_id"]).first() if pending["workstream_id"] else None

    with open(pending["tmp_path"], "rb") as f:
        sheets = read_uploaded_file(f, pending["file_name"])

    if request.method == "POST":
        if "confirm" in request.POST:
            batch = commit_upload(
                project=project,
                workstream_override=workstream,
                sheets=sheets,
                mapping=pending["mapping"],
                uploaded_by=request.user,
                file_name=pending["file_name"],
            )
            Path(pending["tmp_path"]).unlink(missing_ok=True)
            request.session.pop(SESSION_KEY, None)
            messages.success(
                request,
                f"Import complete: {batch.rows_created} created, {batch.rows_updated} updated, "
                f"{batch.rows_skipped} skipped.",
            )
            return redirect("uploads:batch_detail", batch.pk)

        if "cancel" in request.POST:
            Path(pending["tmp_path"]).unlink(missing_ok=True)
            request.session.pop(SESSION_KEY, None)
            messages.info(request, "Upload cancelled.")
            return redirect("uploads:start")

        # Remap: update the stored mapping from the submitted form and re-preview.
        for sheet_name in sheets.keys():
            for field in FIELDS:
                key = f"map__{sheet_name}__{field}"
                if key in request.POST:
                    value = request.POST[key]
                    pending["mapping"].setdefault(sheet_name, {})[field] = value or None
        request.session[SESSION_KEY] = pending
        messages.success(request, "Column mapping updated.")
        return redirect("uploads:preview")

    sheet_previews = []
    for sheet_name, df in sheets.items():
        sheet_mapping = pending["mapping"].get(sheet_name, {})
        default_ws_name = workstream.name if workstream else sheet_name
        parsed_rows = parse_sheet(df, sheet_mapping, default_workstream_name=default_ws_name)
        valid_rows = [r for r in parsed_rows if r.is_valid]
        invalid_rows = [r for r in parsed_rows if not r.is_valid]
        sheet_previews.append(
            {
                "name": sheet_name,
                "headers": list(df.columns),
                "mapping": sheet_mapping,
                "sample": valid_rows[:5],
                "valid_count": len(valid_rows),
                "invalid_rows": invalid_rows[:20],
                "invalid_count": len(invalid_rows),
                "total": len(parsed_rows),
            }
        )

    return render(
        request,
        "uploads/upload_preview.html",
        {
            "project": project,
            "workstream": workstream,
            "file_name": pending["file_name"],
            "fields": FIELDS,
            "sheet_previews": sheet_previews,
        },
    )


@login_required
@user_passes_test(_require_upload_permission)
def upload_history(request):
    batches = UploadBatch.objects.select_related("project", "workstream", "uploaded_by")
    return render(request, "uploads/upload_history.html", {"batches": batches})


@login_required
@user_passes_test(_require_upload_permission)
def upload_batch_detail(request, pk):
    batch = get_object_or_404(UploadBatch.objects.select_related("project", "workstream", "uploaded_by"), pk=pk)
    return render(request, "uploads/upload_batch_detail.html", {"batch": batch})
