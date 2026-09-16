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

                # Subscription Expired and email not sent yet (Note: handled by Stripe mostly, but good for manual checks)
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

            # --- PAST DUE (GRACE PERIOD) CHECK ---
            elif company.subscription_status == 'past_due' or (hasattr(company, 'subscription') and company.subscription.status == 'PAST_DUE'):
                sub = company.subscription
                if sub and sub.current_period_start:
                    days_past_due = (now - sub.current_period_start).days
                    
                    if days_past_due == 4 and sub.status != 'SUSPENDED':
                        # Suspend after 4 days
                        sub.status = 'SUSPENDED'
                        sub.save()
                        company.subscription_status = 'suspended'
                        company.save(update_fields=['subscription_status'])
                        
                        self.send_reminder_email(
                            subject="Account Suspended - Payment Overdue",
                            template_name='billing/email/subscription_suspended.html',
                            context={'company': company},
                            recipient_list=[owner_email]
                        )
                        self.stdout.write(self.style.WARNING(f"Suspended subscription for {company.name} after 4 days grace period."))

                    elif days_past_due >= 8:
                        # Cancel after 8 days
                        import stripe
                        stripe.api_key = settings.STRIPE_SECRET_KEY
                        if sub.stripe_subscription_id:
                            try:
                                stripe.Subscription.delete(sub.stripe_subscription_id)
                                self.stdout.write(self.style.SUCCESS(f"Cancelled Stripe subscription for {company.name}"))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"Failed to cancel Stripe sub: {e}"))
                                
                        sub.status = 'CANCELLED'
                        sub.is_active = False
                        sub.save()
                        company.subscription_status = 'expired'
                        company.save(update_fields=['subscription_status'])
                        
                        self.send_reminder_email(
                            subject="Subscription Cancelled - Invenza ERP",
                            template_name='billing/email/subscription_terminated.html',
                            context={'company': company},
                            recipient_list=[owner_email]
                        )
                        self.stdout.write(self.style.ERROR(f"Cancelled subscription for {company.name} after 8 days past due."))

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
