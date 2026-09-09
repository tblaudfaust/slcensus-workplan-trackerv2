from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode


def send_login_invite(request, user):
    """Emails `user` a one-time link to set their own password and log
    in, reusing the exact same token mechanism as the "forgot password"
    flow (django.contrib.auth's default_token_generator + uid/token, sent
    through accounts:password_reset_confirm) rather than an admin
    inventing a password for them. Used both right after an admin
    creates a new account and to (re)send that link at any time from
    User Management. Returns True if an email was sent, False if the
    user has no email on file to send it to."""
    if not user.email:
        return False

    context = {
        "user": user,
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
        "protocol": "https" if request.is_secure() else "http",
        "domain": request.get_host(),
        "site_name": settings.SITE_NAME,
    }
    html_body = render_to_string("accounts/invite_email.html", context)
    text_body = strip_tags(html_body)
    message = EmailMultiAlternatives(f"[{settings.SITE_NAME}] Your account is ready", text_body, to=[user.email])
    message.attach_alternative(html_body, "text/html")
    message.send()
    return True
