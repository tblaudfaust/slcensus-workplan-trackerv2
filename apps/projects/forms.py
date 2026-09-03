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
        fields = ["name", "description", "census_year", "census_day", "owner", "is_active"]
        widgets = {"census_day": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = User.objects.filter(
            role__in=[Role.ADMIN, Role.PROJECT_OWNER], is_active=True
        )


class WorkstreamForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Workstream
        fields = ["name", "description", "lead", "members"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lead"].queryset = User.objects.filter(is_active=True)
        self.fields["members"].queryset = User.objects.filter(is_active=True)
