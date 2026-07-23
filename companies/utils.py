from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.core.signing import TimestampSigner

signer = TimestampSigner()

def generate_verification_token(user_id):
    return signer.sign(str(user_id))

def verify_token(token, max_age=86400): # 24 hours
    try:
        user_id = signer.unsign(token, max_age=max_age)
        return int(user_id)
    except Exception:
        return None

def send_html_email(subject, template_name, context, to_email):
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_verification_email(user, frontend_url):
    token = generate_verification_token(user.id)
    verify_url = f"{frontend_url}/verify-email?token={token}"
    
    context = {
        'user': user,
        'verify_url': verify_url
    }
    send_html_email(
        subject="Verify your Invenza Account",
        template_name="emails/verify_email.html",
        context=context,
        to_email=user.email
    )

def send_welcome_email(user, company, temp_erp_pass):
    context = {
        'user': user,
        'company': company,
        'temp_erp_pass': temp_erp_pass
    }
    send_html_email(
        subject="Welcome to Invenza!",
        template_name="emails/welcome_email.html",
        context=context,
        to_email=user.email
    )

def send_password_reset_email(user, frontend_url):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    
    reset_url = f"{frontend_url}/reset-password?uid={uid}&token={token}"
    
    context = {
        'user': user,
        'reset_url': reset_url
    }
    send_html_email(
        subject="Reset your Invenza Password",
        template_name="emails/reset_password.html",
        context=context,
        to_email=user.email
    )

def send_password_changed_email(user):
    context = {
        'user': user
    }
    send_html_email(
        subject="Your Invenza Password has been changed",
        template_name="emails/password_changed.html",
        context=context,
        to_email=user.email
    )
