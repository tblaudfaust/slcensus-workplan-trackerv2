from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.shortcuts import get_object_or_404, redirect, render

from . import permissions
from .forms import LoginForm, UserCreateForm, UserUpdateForm
from .models import User


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    authentication_form = LoginForm


class LogoutView(auth_views.LogoutView):
    pass


def _require_admin(user):
    return permissions.can_manage_users(user)


@login_required
@user_passes_test(_require_admin)
def user_list(request):
    users = User.objects.all()
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@user_passes_test(_require_admin)
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"User {user.username} created.")
            return redirect("accounts:user_list")
    else:
        form = UserCreateForm()
    return render(request, "accounts/user_form.html", {"form": form, "is_create": True})


@login_required
@user_passes_test(_require_admin)
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=target)
        if form.is_valid():
            form.save()
            messages.success(request, f"User {target.username} updated.")
            return redirect("accounts:user_list")
    else:
        form = UserUpdateForm(instance=target)
    return render(request, "accounts/user_form.html", {"form": form, "is_create": False, "target": target})


@login_required
@user_passes_test(_require_admin)
def user_reset_password(request, pk):
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = AdminPasswordChangeForm(target, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Password reset for {target.username}.")
            return redirect("accounts:user_list")
    else:
        form = AdminPasswordChangeForm(target)
    return render(request, "accounts/user_password_form.html", {"form": form, "target": target})


@login_required
@user_passes_test(_require_admin)
def user_toggle_active(request, pk):
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST" and target.pk != request.user.pk:
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        messages.success(request, f"{target.username} is now {'active' if target.is_active else 'inactive'}.")
    return redirect("accounts:user_list")
