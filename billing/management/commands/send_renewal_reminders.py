from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from billing.models import Subscription
from companies.models import Company
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

class Command(BaseCommand):
    help = 'Send subscription renewal reminders and expiration notices'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        
        # 1. Send Expiry Reminders (7 days, 3 days, 1 day)
        for days_left in [7, 3, 1]:
            target_date = now + timedelta(days=days_left)
            
            # Find subscriptions expiring on this target_date (by matching the date part)
            expiring_subs = Subscription.objects.filter(
                status='ACTIVE',
                expiry_date__date=target_date.date()
            )
            
            for sub in expiring_subs:
                company = sub.company
                if not company.user or not company.user.email:
                    continue
                
                self.send_email(
                    to_email=company.user.email,
                    company_name=company.name,
                    plan_name=sub.plan.name if sub.plan else 'Custom',
                    expiry_date=sub.expiry_date,
                    days_left=days_left,
                    is_expired=False
                )
                self.stdout.write(self.style.SUCCESS(f'Sent {days_left}-day reminder to {company.user.email}'))
                
        # 2. Send Expired Notices (expired today)
        expired_subs = Subscription.objects.filter(
            status='ACTIVE',
            expiry_date__date=now.date()
        )
        
        for sub in expired_subs:
            company = sub.company
            
            # Optionally update status here
            sub.status = 'EXPIRED'
            sub.save()
            
            # Also update legacy company fields for safety
            company.subscription_status = 'expired'
            company.save()
            
            if not company.user or not company.user.email:
                continue
                
            self.send_email(
                to_email=company.user.email,
                company_name=company.name,
                plan_name=sub.plan.name if sub.plan else 'Custom',
                expiry_date=sub.expiry_date,
                days_left=0,
                is_expired=True
            )
            self.stdout.write(self.style.SUCCESS(f'Sent expiration notice to {company.user.email}'))

    def send_email(self, to_email, company_name, plan_name, expiry_date, days_left, is_expired):
        subject = 'Action Required: Subscription Expired' if is_expired else f'Reminder: Subscription expires in {days_left} days'
        
        # Note: adjust dashboard_url if needed based on your domains
        dashboard_url = 'https://invenza-erp.cloud/portal/pricing'
        
        context = {
            'company_name': company_name,
            'plan_name': plan_name,
            'expiry_date': expiry_date,
            'days_left': days_left,
            'is_expired': is_expired,
            'dashboard_url': dashboard_url,
        }
        
        html_content = render_to_string('billing/email/renewal_reminder.html', context)
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Your subscription is {'expired' if is_expired else f'expiring in {days_left} days'}. Please renew at {dashboard_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
