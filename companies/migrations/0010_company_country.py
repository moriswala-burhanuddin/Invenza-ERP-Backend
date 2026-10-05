from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0009_company_stripe_customer_id_and_more'),
    ]

    operations = [
        # Nullable, no default: existing companies are untouched and keep working.
        migrations.AddField(
            model_name='company',
            name='country',
            field=models.CharField(blank=True, help_text='ISO 3166-1 alpha-2 country code (e.g. GB)', max_length=2, null=True),
        ),
    ]
