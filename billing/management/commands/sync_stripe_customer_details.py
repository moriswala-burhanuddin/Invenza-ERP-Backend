"""
Backfill Stripe customers with the phone + country stored in our DB.

Existing Stripe customers created before checkout collected phone/country show
"-" for both. This pushes whatever we have on the Company to Stripe.
Companies with no phone/country are skipped (nothing to send).

Usage:
    python manage.py sync_stripe_customer_details --dry-run
    python manage.py sync_stripe_customer_details
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from companies.models import Company
from billing import stripe_service


class Command(BaseCommand):
    help = "Push phone + country from Company records to existing Stripe customers."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='List what would be synced without calling Stripe.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        companies = Company.objects.filter(stripe_customer_id__isnull=False).exclude(stripe_customer_id='').filter(
            Q(phone__isnull=False, phone__gt='') | Q(country__isnull=False, country__gt='')
        )

        synced = failed = 0
        for company in companies:
            label = f"{company.name} ({company.stripe_customer_id}) phone={company.phone or '-'} country={company.country or '-'}"
            if dry_run:
                self.stdout.write(f"[dry-run] {label}")
                continue
            if stripe_service.sync_customer_details(company):
                synced += 1
                self.stdout.write(self.style.SUCCESS(f"Synced {label}"))
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"Failed {label}"))

        if not dry_run:
            self.stdout.write(f"Done. Synced: {synced}, failed: {failed}")
