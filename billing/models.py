from django.db import models
from django.contrib.auth.models import User
from companies.models import Company

class Plan(models.Model):
    INTERVAL_CHOICES = [
        ('year', 'Annual'),
    ]

    name = models.CharField(max_length=100)  # e.g. Silver, Gold, Platinum
    stripe_price_id = models.CharField(max_length=100, blank=True, null=True, help_text="Stripe Price ID (price_xxx)")
    stripe_product_id = models.CharField(max_length=100, blank=True, null=True, help_text="Stripe Product ID (prod_xxx)")
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Legacy price in GBP", default=0.00)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Annual price in GBP (e.g. 500)")
    billing_interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='year')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    trial_period_days = models.IntegerField(default=7, help_text="Free trial days for new subscribers")

    # Legacy Razorpay field (preserved for historical reference)
    price_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.name} - £{self.monthly_price}/mo"

    @property
    def annual_price_calculated(self):
        """Returns annual price: uses override if set, otherwise monthly × 12."""
        if self.annual_price:
            return self.annual_price
        return self.monthly_price * 12


class Feature(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    internal_id = models.CharField(max_length=50, unique=True, help_text="e.g. ai_assistant")

    def __str__(self):
        return self.name


class Payment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CREATED', 'Created'),
        ('AUTHORIZED', 'Authorized'),
        ('CAPTURED', 'Captured'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('razorpay', 'Razorpay'),
        ('manual', 'Manual'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='payments')
    amount = models.IntegerField(help_text="Amount in smallest currency unit (pence for GBP)")
    currency = models.CharField(max_length=10, default='GBP')
    plan_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, default='stripe')
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    # Stripe fields
    stripe_payment_intent_id = models.CharField(max_length=100, null=True, blank=True)
    stripe_invoice_id = models.CharField(max_length=100, null=True, blank=True)
    stripe_charge_id = models.CharField(max_length=100, null=True, blank=True)

    # Legacy Razorpay fields (preserved for historical data)
    razorpay_order_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Payment {self.id} - {self.company.name} - {self.status}"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('TRIAL', 'Trial'),
        ('ACTIVE', 'Active'),
        ('GRACE', 'Grace Period'),
        ('PAST_DUE', 'Past Due'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
        ('SUSPENDED', 'Suspended'),
        ('INCOMPLETE', 'Incomplete'),
    ]
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    features = models.ManyToManyField(Feature, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TRIAL')
    start_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    auto_renew = models.BooleanField(default=True)
    last_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')

    # Stripe subscription fields
    stripe_subscription_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    stripe_customer_id = models.CharField(max_length=100, null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    billing_interval = models.CharField(max_length=10, default='month', choices=[('month', 'Monthly'), ('year', 'Annual')])

    # Legacy fields (preserved for historical data)
    order_id = models.CharField(max_length=100, blank=True, null=True)
    payment_id = models.CharField(max_length=100, blank=True, null=True)
    receipt_number = models.CharField(max_length=50, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.company.name} - {self.status}"

    @property
    def is_subscription_active(self):
        """Returns True if the subscription is in a usable state."""
        return self.status in ['TRIAL', 'ACTIVE', 'GRACE']


class Invoice(models.Model):
    invoice_no = models.CharField(max_length=50, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='invoice')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    pdf_path = models.FileField(upload_to='invoices/', null=True, blank=True)
    stripe_invoice_url = models.URLField(null=True, blank=True, help_text="Link to Stripe-hosted invoice")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.invoice_no


class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100, default='', help_text="e.g. invoice.paid, checkout.session.completed")
    payload = models.JSONField()
    signature = models.CharField(max_length=255, null=True, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='PROCESSED')

    def __str__(self):
        return f"{self.event_type} - {self.event_id}"


class SubscriptionAuditLog(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=50)
    details = models.JSONField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.company.name} - {self.action}"
