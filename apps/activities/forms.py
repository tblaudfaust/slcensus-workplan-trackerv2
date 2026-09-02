from django import forms

from apps.accounts.models import User
from apps.projects.models import Workstream

from .models import Activity, Comment


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.setdefault("class", "form-control")
                field.widget.attrs.setdefault("type", "date")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class ActivityForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            "workstream",
            "name",
            "start_date",
            "end_date",
            "duration_days",
            "dependency",
            "deliverable",
            "responsible",
            "responsible_text",
            "status",
            "progress_percent",
            "phase",
            "remarks",
            "is_milestone",
        ]
        widgets = {
            "start_date": forms.DateInput(),
            "end_date": forms.DateInput(),
            "dependency": forms.Textarea(attrs={"rows": 2}),
            "deliverable": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            self.fields["workstream"].queryset = Workstream.objects.filter(project=project)
        self.fields["responsible"].queryset = User.objects.filter(is_active=True)
        self.fields["responsible"].required = False

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date cannot be before the start date.")
        progress = cleaned.get("progress_percent")
        if progress is not None and not (0 <= progress <= 100):
            self.add_error("progress_percent", "Progress must be between 0 and 100.")
        return cleaned


class RestrictedActivityForm(ActivityForm):
    """Used by Contributors: they may update status/progress/remarks on an
    activity they own, but not reassign it or rewrite its schedule."""

    class Meta(ActivityForm.Meta):
        fields = ["status", "progress_percent", "remarks"]


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 2, "class": "form-control", "placeholder": "Add an update or comment..."})}


class ActivityFilterForm(forms.Form):
    q = forms.CharField(required=False)
    workstream = forms.ModelChoiceField(queryset=Workstream.objects.none(), required=False)
    responsible = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    status = forms.ChoiceField(required=False, choices=[])
    phase = forms.CharField(required=False)
    start_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    start_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    overdue_only = forms.BooleanField(required=False)
    unassigned_only = forms.BooleanField(required=False)

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Status

        if project is not None:
            self.fields["workstream"].queryset = Workstream.objects.filter(project=project)
            self.fields["responsible"].queryset = User.objects.filter(
                responsible_activities__project=project
            ).distinct()
        self.fields["status"].choices = [("", "Any status")] + list(Status.choices)
        for name, field in self.fields.items():
            if name in ("overdue_only", "unassigned_only"):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select form-select-sm")
            else:
                field.widget.attrs.setdefault("class", "form-control form-control-sm")
