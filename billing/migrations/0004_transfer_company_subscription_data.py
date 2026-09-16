from django.db import migrations

def transfer_subscription_data(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    Subscription = apps.get_model('billing', 'Subscription')

    for company in Company.objects.all():
        # Get or create subscription
        subscription, created = Subscription.objects.get_or_create(company=company)

        # Map company.subscription_status to billing.Subscription.status
        # Note: Company model has choices ['trial', 'active', 'expired']
        company_status = getattr(company, 'subscription_status', 'trial').upper()
        
        if company_status in ['TRIAL', 'ACTIVE', 'EXPIRED']:
            subscription.status = company_status
        else:
            subscription.status = 'TRIAL'
            
        # Copy expiry date
        if getattr(company, 'expiry_date', None):
            subscription.expiry_date = company.expiry_date

        subscription.save()

class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_webhookevent_subscription_auto_renew_and_more'),
        ('companies', '0008_company_reminder_email_sent'), # Ensure companies app is loaded
    ]

    operations = [
        migrations.RunPython(transfer_subscription_data),
    ]

