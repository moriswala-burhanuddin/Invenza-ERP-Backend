from django.core.mail import EmailMessage
from django.conf import settings
from .models import ERPUser
import os

class EnterpriseEmailService:
    @staticmethod
    def send_supplier_email(user, supplier_email, subject, message, attachments=None):
        """
        Sends an email to a supplier.
        Uses the user's name in the From field and their email in Reply-To.
        """
        # Fallback to defaults if user has no email
        from_name = user.name or "ERP Support"
        reply_to_email = user.email or settings.DEFAULT_FROM_EMAIL
        
        # Build the From header properly: "Name <default_email>"
        # This keeps the SMTP provider happy while showing the user's name
        formatted_from = f"{from_name} <{settings.DEFAULT_FROM_EMAIL}>"
        
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=formatted_from,
            to=[supplier_email],
            reply_to=[reply_to_email],
        )
        
        if attachments:
            for attach in attachments:
                # Assuming attach is a dict with 'name', 'content', 'mimetype'
                email.attach(attach['name'], attach['content'], attach['mimetype'])
        
        return email.send()

    @staticmethod
    def send_billing_email(company_email, subject, message):
        """
        Sends a system/billing email.
        """
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[company_email],
        )
        return email.send()
