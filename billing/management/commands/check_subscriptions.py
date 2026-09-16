from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from billing.models import Subscription, SubscriptionAuditLog
from billing import stripe_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Checks subscriptions and updates statuses. Also syncs with Stripe for active subscriptions.'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        
        # 1. Sync Stripe subscriptions that may have drifted
        stripe_subs = Subscription.objects.filter(
            stripe_subscription_id__isnull=False,
            status__in=['ACTIVE', 'TRIAL', 'PAST_DUE']
        )
        
        for sub in stripe_subs:
            try:
                stripe_data = stripe_service.sync_subscription_from_stripe(sub.stripe_subscription_id)
                old_status = sub.status
                sub.status = stripe_data['status']
                sub.current_period_start = stripe_data['current_period_start']
                sub.current_period_end = stripe_data['current_period_end']
                sub.cancel_at_period_end = stripe_data['cancel_at_period_end']
                sub.expiry_date = stripe_data['current_period_end']
                sub.save()
                
                if old_status != sub.status:
                    self.stdout.write(f"Company {sub.company.name}: {old_status} → {sub.status}")
                    SubscriptionAuditLog.objects.create(
                        company=sub.company,
                        action='STRIPE_SYNC',
                        details={
                            'old_status': old_status,
                            'new_status': sub.status,
                            'stripe_subscription_id': sub.stripe_subscription_id,
                        }
                    )
            except Exception as e:
                logger.error(f"Error syncing subscription for {sub.company.name}: {e}")
                self.stderr.write(f"Error syncing {sub.company.name}: {e}")

        # 2. Handle Grace Period for non-Stripe subscriptions (legacy Razorpay)
        grace_start = now - timedelta(days=3)
        grace_subs = Subscription.objects.filter(
            stripe_subscription_id__isnull=True,
            status__in=['ACTIVE', 'TRIAL'],
            expiry_date__lt=now,
            expiry_date__gte=grace_start
        )
        
        for sub in grace_subs:
            sub.status = 'GRACE'
            sub.save()
            SubscriptionAuditLog.objects.create(
                company=sub.company,
                action='ENTERED_GRACE_PERIOD',
                details={'expiry_date': str(sub.expiry_date)}
            )
            self.stdout.write(f"Company {sub.company.name} entered GRACE period.")

        # 3. Handle Expiry for non-Stripe subscriptions (legacy Razorpay)
        expired_subs = Subscription.objects.filter(
            stripe_subscription_id__isnull=True,
            status__in=['ACTIVE', 'TRIAL', 'GRACE'],
            expiry_date__lt=grace_start
        )
        
        for sub in expired_subs:
            sub.status = 'EXPIRED'
            sub.save()
            SubscriptionAuditLog.objects.create(
                company=sub.company,
                action='SUBSCRIPTION_EXPIRED',
                details={'expiry_date': str(sub.expiry_date)}
            )
            self.stdout.write(f"Company {sub.company.name} EXPIRED.")

        self.stdout.write(self.style.SUCCESS('Successfully completed subscription checks'))
