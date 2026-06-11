from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_welcome_email(user, company, erp_password):
    """
    Sends a welcome email to the newly registered company owner with their
    ERP access credentials.
    """
    subject = f"Welcome to Invenza ERP - Your Login Credentials"
    message = (
        f"Hello {user.username},\n\n"
        f"Thank you for signing up with Invenza ERP!\n"
        f"Your company '{company.name}' has been successfully created.\n\n"
        f"Here are your access credentials for the Desktop ERP Application:\n"
        f"Login ID (Company ID): {company.id}\n"
        f"Temporary Password: {erp_password}\n\n"
        f"We recommend changing this password upon first login.\n\n"
        f"Best Regards,\n"
        f"The Invenza Team"
    )
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"Welcome email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {e}")
