from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from billing.models import Subscription
from django.core.mail import send_mail

class Command(BaseCommand):
    help = 'Check for subscriptions expiring in 7 days and send warning emails.'

    def handle(self, *args, **options):
        target_date = (timezone.now() + timedelta(days=7)).date()
        
        # We need to filter based on the date part of expiry_date
        expirying_soon = Subscription.objects.filter(
            expiry_date__date=target_date,
            is_active=True
        )

        self.stdout.write(f"Checking for expiries on {target_date}...")
        self.stdout.write(f"Found {expirying_soon.count()} subscriptions expiring soon.")

        for sub in expirying_soon:
            try:
                send_mail(
                    'Your Invenza ERP Subscription Expires in 7 Days',
                    f'Hello {sub.company.name},\n\n'
                    f'Your subscription to the {sub.plan.name} plan will expire on {sub.expiry_date.strftime("%Y-%m-%d")}.\n'
                    f'To avoid any service interruption, please renew your plan from the dashboard.\n\n'
                    f'Login Identifier: {sub.company.id}\n\n'
                    f'Thank you,\n'
                    f'The Invenza Team',
                    'support@invenza.erp',
                    [sub.company.email],
                    fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(f"Sent warning to {sub.company.email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to send to {sub.company.email}: {e}"))
