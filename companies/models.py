from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_companies')
    
    # Professional Profile Fields
    legal_name = models.CharField(max_length=255, null=True, blank=True)
    tax_id = models.CharField(max_length=100, null=True, blank=True, help_text="GST / PAN / VAT")
    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=20, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    website = models.URLField(null=True, blank=True)
    base_currency = models.CharField(max_length=10, default='UGX', help_text="Default display currency")
    
    # SaaS & Feature Flags
    is_ai_enabled = models.BooleanField(default=False)
    subscription_status = models.CharField(
        max_length=50, 
        choices=[('trial', 'Trial'), ('active', 'Active'), ('expired', 'Expired')],
        default='trial'
    )
    expiry_date = models.DateTimeField(null=True, blank=True)
    razorpay_customer_id = models.CharField(max_length=100, null=True, blank=True)
    erp_password = models.CharField(max_length=128, null=True, blank=True, help_text="Temporary password for desktop ERP access")

    @property
    def trial_days_left(self):
        from django.utils import timezone
        import datetime
        trial_duration = datetime.timedelta(days=7)
        expiry = self.created_at + trial_duration
        remaining = expiry - timezone.now()
        return max(0, remaining.days)

    @property
    def is_trial_active(self):
        return self.subscription_status == 'trial' and self.trial_days_left > 0

    def __str__(self):
        return self.name

class TenantModel(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

    class Meta:
        abstract = True
