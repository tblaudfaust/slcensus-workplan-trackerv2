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
        # Populate every workstream up front (labelled with its project via
        # Workstream.__str__) so the dropdown has real choices on the very
        # first page load -- it used to stay empty until the form was
        # POSTed once, since the queryset was only narrowed from data that
        # doesn't exist yet on a fresh GET, making it impossible to select
        # a workstream on a first attempt.
        self.fields["workstream"].queryset = Workstream.objects.filter(project__is_active=True).select_related(
            "project"
        )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Only .xlsx and .csv files are supported.")
        return f
