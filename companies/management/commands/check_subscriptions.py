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
            
            # --- TRIAL LOGIC ---
            if company.subscription_status == 'trial':
                days_left = company.trial_days_left
                
                # 1 Day Left Reminder
                if days_left == 1 and not company.trial_reminder_sent:
                    self.send_reminder_email(
                        subject=f"Your Invenza Trial Ends Tomorrow",
                        template_name='emails/trial_reminder.html',
                        context={'company': company, 'days_left': days_left},
                        recipient_list=[owner_email]
                    )
                    company.trial_reminder_sent = True
                    company.save()
                    self.stdout.write(self.style.SUCCESS(f"Sent trial reminder to {owner_email}"))

                # Trial Expired
                elif days_left <= 0:
                    company.subscription_status = 'expired'
                    company.trial_reminder_sent = False # reset
                    company.save()
                    
                    self.send_reminder_email(
                        subject=f"Your Invenza Trial Has Expired",
                        template_name='emails/trial_expired.html',
                        context={'company': company},
                        recipient_list=[owner_email]
                    )
                    self.stdout.write(self.style.SUCCESS(f"Expired trial for {owner_email}"))


            # --- ACTIVE LOGIC ---
            elif company.subscription_status == 'active':
                if not company.expiry_date:
                    continue # Lifetime or unexpiring plan
                    
                days_left = (company.expiry_date - now).days
                
                # 1 Day Left Reminder
                if days_left == 1 and not company.subscription_reminder_sent:
                    self.send_reminder_email(
                        subject=f"Your Invenza Subscription Renews Tomorrow",
                        template_name='emails/subscription_reminder.html',
                        context={'company': company, 'days_left': days_left},
                        recipient_list=[owner_email]
                    )
                    company.subscription_reminder_sent = True
                    company.save()
                    self.stdout.write(self.style.SUCCESS(f"Sent subscription reminder to {owner_email}"))
                    
                # Subscription Expired
                elif days_left < 0:
                    company.subscription_status = 'expired'
                    company.subscription_reminder_sent = False # reset
                    company.save()
                    
                    self.send_reminder_email(
                        subject=f"Your Invenza Subscription Has Expired",
                        template_name='emails/subscription_expired.html',
                        context={'company': company},
                        recipient_list=[owner_email]
                    )
                    self.stdout.write(self.style.SUCCESS(f"Expired subscription for {owner_email}"))

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
