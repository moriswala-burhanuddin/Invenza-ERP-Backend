from django.db import models
from companies.models import Company

class Plan(models.Model):
    name = models.CharField(max_length=100) # e.g. Silver, Gold
    price_id = models.CharField(max_length=100, blank=True, null=True) # Razorpay Plan ID if needed
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - ${self.monthly_price}"

class Feature(models.Model):
    name = models.CharField(max_length=100) # e.g. AI Assistant, Advanced Reports
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    internal_id = models.CharField(max_length=50, unique=True, help_text="e.g. ai_assistant")

    def __str__(self):
        return self.name

class Subscription(models.Model):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    features = models.ManyToManyField(Feature, blank=True)
    
    start_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    
    # Razorpay tracking
    order_id = models.CharField(max_length=100, blank=True, null=True)
    payment_id = models.CharField(max_length=100, blank=True, null=True)
    receipt_number = models.CharField(max_length=50, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.company.name} - {self.plan.name if self.plan else 'No Plan'}"
