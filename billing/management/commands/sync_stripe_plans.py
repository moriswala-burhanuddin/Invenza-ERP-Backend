"""
Management command to sync local Plan records to Stripe Products & Prices.
Creates Stripe Products and Prices for each Plan and stores the IDs.
Only creates annual variants as requested by client.

Usage:
    python manage.py sync_stripe_plans
    python manage.py sync_stripe_plans --dry-run
"""

import stripe
from django.core.management.base import BaseCommand
from django.conf import settings
from billing.models import Plan


class Command(BaseCommand):
    help = 'Syncs local Plan records to Stripe Products & Prices (annual only)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be created without actually calling Stripe',
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        currency = getattr(settings, 'STRIPE_CURRENCY', 'gbp')
        dry_run = options['dry_run']

        if not stripe.api_key:
            self.stderr.write(self.style.ERROR('STRIPE_SECRET_KEY is not set. Add it to your .env file.'))
            return

        # Get plans
        plans = Plan.objects.filter(is_active=True)

        if not plans.exists():
            self.stdout.write(self.style.WARNING('No active plans found. Seed your plans first.'))
            return

        for plan in plans:
            self.stdout.write(f"\n{'='*50}")
            self.stdout.write(f"Processing plan: {plan.name}")

            # ── Step 1: Create or retrieve Stripe Product ──
            if plan.stripe_product_id:
                self.stdout.write(f"  Product already exists: {plan.stripe_product_id}")
                product_id = plan.stripe_product_id
            else:
                if dry_run:
                    self.stdout.write(f"  [DRY RUN] Would create Stripe Product: {plan.name}")
                    product_id = 'prod_dry_run'
                else:
                    product = stripe.Product.create(
                        name=f"Invenza ERP - {plan.name}",
                        description=plan.description or f"{plan.name} subscription plan",
                        metadata={'plan_name': plan.name, 'local_plan_id': str(plan.id)},
                    )
                    product_id = product.id
                    plan.stripe_product_id = product_id
                    plan.save(update_fields=['stripe_product_id'])
                    self.stdout.write(self.style.SUCCESS(f"  Created Stripe Product: {product_id}"))

            # ── Step 2: Create annual Stripe Price ──
            # Use annual_price if set, otherwise default to £500 as per client request
            annual_price_val = plan.annual_price if plan.annual_price else 500.00
            annual_amount = int(annual_price_val * 100)  # Convert to pence

            if plan.stripe_price_id:
                self.stdout.write(f"  Annual Price already exists: {plan.stripe_price_id}")
            else:
                if dry_run:
                    self.stdout.write(f"  [DRY RUN] Would create annual Price: £{annual_price_val}/year")
                else:
                    price = stripe.Price.create(
                        product=product_id,
                        unit_amount=annual_amount,
                        currency=currency,
                        recurring={'interval': 'year'},
                        metadata={'plan_name': plan.name, 'interval': 'year'},
                    )
                    plan.stripe_price_id = price.id
                    plan.billing_interval = 'year'
                    plan.save(update_fields=['stripe_price_id', 'billing_interval'])
                    self.stdout.write(self.style.SUCCESS(f"  Created annual Price: {price.id} (£{annual_price_val}/year)"))

        self.stdout.write(f"\n{'='*50}")
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN complete. No changes were made to Stripe.'))
        else:
            self.stdout.write(self.style.SUCCESS('All plans synced to Stripe successfully!'))
