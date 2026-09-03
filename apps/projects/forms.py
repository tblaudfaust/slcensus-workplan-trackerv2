from django import forms

from apps.accounts.models import Role, User

from .models import Project, Workstream


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class ProjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "census_year", "census_day", "owner", "co_owner", "is_active"]
        widgets = {"census_day": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        owner_pool = User.objects.filter(role__in=[Role.ADMIN, Role.PROJECT_OWNER], is_active=True)
        self.fields["owner"].queryset = owner_pool
        self.fields["co_owner"].queryset = owner_pool

    def clean(self):
        cleaned = super().clean()
        owner, co_owner = cleaned.get("owner"), cleaned.get("co_owner")
        if owner and co_owner and owner == co_owner:
            self.add_error("co_owner", "Co-owner must be a different person than the owner.")
        return cleaned


class WorkstreamForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Workstream
        fields = ["name", "description", "lead", "backup_lead", "members"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lead"].queryset = User.objects.filter(is_active=True)
        self.fields["backup_lead"].queryset = User.objects.filter(is_active=True)
        self.fields["members"].queryset = User.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        lead, backup = cleaned.get("lead"), cleaned.get("backup_lead")
        if lead and backup and lead == backup:
            self.add_error("backup_lead", "Backup lead must be a different person than the lead.")
        return cleaned
