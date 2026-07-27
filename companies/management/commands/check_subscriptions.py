import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from companies.models import Company
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

class Command(BaseCommand):
    help = 'Checks subscription and trial expirations, updates statuses, and sends emails'

    def handle(self, *args, **options):
        now = timezone.now()
        companies = Company.objects.all()
        
        for company in companies:
            owner_email = company.owner.email
            
            # --- TRIAL EXPIRATION CHECK ---
            if company.subscription_status == 'trial':
                days_left = company.trial_days_left
                
                # 1 Day Left Reminder
                if days_left == 1 and not company.reminder_email_sent:
                    self.send_reminder_email(
                        subject="Your Invenza Trial Ends Tomorrow",
                        template_name='emails/trial_reminder.html',
                        context={'company': company, 'days_left': days_left},
                        recipient_list=[owner_email]
                    )
                    company.reminder_email_sent = True
                    company.save(update_fields=['reminder_email_sent'])
                    self.stdout.write(self.style.SUCCESS(f"Sent trial reminder email to {owner_email}"))
                
                # Trial Expired and email not sent yet
                elif days_left <= 0 and not company.expiry_email_sent:
                    self.send_reminder_email(
                        subject="Your Invenza Trial Has Expired",
                        template_name='emails/trial_expired.html',
                        context={'company': company},
                        recipient_list=[owner_email]
                    )
                    company.expiry_email_sent = True
                    company.save(update_fields=['expiry_email_sent'])
                    self.stdout.write(self.style.SUCCESS(f"Sent trial expiry email to {owner_email}"))

            # --- ACTIVE SUBSCRIPTION EXPIRATION CHECK ---
            elif company.subscription_status == 'active':
                if not company.expiry_date:
                    continue # Lifetime or unexpiring plan
                    
                days_left = (company.expiry_date - now).days
                
                # 6 Days Left Reminder
                if days_left == 6 and not company.reminder_email_sent:
                    self.send_reminder_email(
                        subject="Your Invenza Subscription Renews Soon",
                        template_name='emails/subscription_reminder.html',
                        context={'company': company, 'days_left': days_left},
                        recipient_list=[owner_email]
                    )
                    company.reminder_email_sent = True
                    company.save(update_fields=['reminder_email_sent'])
                    self.stdout.write(self.style.SUCCESS(f"Sent subscription reminder email to {owner_email}"))

                # Subscription Expired and email not sent yet
                elif days_left < 0 and not company.expiry_email_sent:
                    self.send_reminder_email(
                        subject="Your Invenza Subscription Has Expired",
                        template_name='emails/subscription_expired.html',
                        context={'company': company},
                        recipient_list=[owner_email]
                    )
                    company.expiry_email_sent = True
                    company.save(update_fields=['expiry_email_sent'])
                    self.stdout.write(self.style.SUCCESS(f"Sent subscription expiry email to {owner_email}"))

        self.stdout.write(self.style.SUCCESS('Successfully completed subscription check.'))


    def send_reminder_email(self, subject, template_name, context, recipient_list):
        try:
            html_message = render_to_string(template_name, context)
            send_mail(
                subject=subject,
                message="",
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                fail_silently=False,
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error sending email: {e}"))
