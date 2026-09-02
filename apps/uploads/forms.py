from django import forms

from apps.projects.models import Project, Workstream


class UploadForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.filter(is_active=True))
    workstream = forms.ModelChoiceField(
        queryset=Workstream.objects.none(),
        required=False,
        help_text="Leave blank to import a full workbook (each worksheet becomes/updates its own workstream).",
    )
    file = forms.FileField(help_text="Accepted formats: .xlsx, .csv")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["project"].widget.attrs["class"] = "form-select"
        self.fields["workstream"].widget.attrs["class"] = "form-select"
        if "project" in self.data:
            try:
                project_id = int(self.data.get("project"))
                self.fields["workstream"].queryset = Workstream.objects.filter(project_id=project_id)
            except (TypeError, ValueError):
                pass
        elif self.initial.get("project"):
            self.fields["workstream"].queryset = Workstream.objects.filter(project=self.initial["project"])

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Only .xlsx and .csv files are supported.")
        return f
