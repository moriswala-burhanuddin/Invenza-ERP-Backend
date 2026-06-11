import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()

from billing.models import Plan, Feature

def seed():
    # Plans
    silver, _ = Plan.objects.get_or_create(
        name="Silver",
        monthly_price=2999.00,
        description="Core ERP features for small businesses."
    )
    gold, _ = Plan.objects.get_or_create(
        name="Gold",
        monthly_price=5999.00,
        description="Advanced inventory and multi-user support."
    )
    platinum, _ = Plan.objects.get_or_create(
        name="Platinum",
        monthly_price=9999.00,
        description="Unlimited scale with high-priority support."
    )

    # Features
    ai, _ = Feature.objects.get_or_create(
        name="AI Assistant",
        internal_id="ai_assistant",
        price=999.00,
        description="Smart inventory forecasting and automated insights."
    )
    reports, _ = Feature.objects.get_or_create(
        name="Advanced Reports",
        internal_id="adv_reports",
        price=499.00,
        description="Custom financial dashboards and export capabilities."
    )

    print("Billing data seeded successfully!")

if __name__ == "__main__":
    seed()
