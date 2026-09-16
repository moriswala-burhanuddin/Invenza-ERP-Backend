from django.contrib import admin
from .models import Plan, Feature, Subscription, Payment, Invoice, WebhookEvent, SubscriptionAuditLog

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'monthly_price', 'annual_price', 'billing_interval', 'stripe_price_id', 'trial_period_days', 'is_active')
    list_filter = ('billing_interval', 'is_active')
    search_fields = ('name', 'stripe_price_id', 'stripe_product_id')

@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active', 'internal_id')
    search_fields = ('name', 'internal_id')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'get_user', 'status', 'plan', 'billing_interval', 'current_period_end', 'cancel_at_period_end', 'auto_renew', 'stripe_subscription_id')
    list_filter = ('status', 'billing_interval', 'auto_renew', 'cancel_at_period_end')
    search_fields = ('company__name', 'stripe_subscription_id', 'stripe_customer_id', 'company__owner__email', 'company__owner__username')
    readonly_fields = ('stripe_subscription_id', 'stripe_customer_id')

    def get_user(self, obj):
        return obj.company.owner.email if obj.company and hasattr(obj.company, 'owner') and obj.company.owner else '-'
    get_user.short_description = 'User (Owner)'
    get_user.admin_order_field = 'company__owner__email'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'company', 'user', 'get_plan', 'amount', 'currency', 'payment_method', 'status', 'created_at')
    list_filter = ('status', 'payment_method')
    search_fields = ('company__name', 'user__email', 'user__username', 'stripe_payment_intent_id', 'stripe_invoice_id', 'razorpay_order_id', 'razorpay_payment_id')

    def get_plan(self, obj):
        if obj.plan_id:
            try:
                return Plan.objects.get(id=obj.plan_id).name
            except Plan.DoesNotExist:
                return f"ID: {obj.plan_id}"
        return "-"
    get_plan.short_description = "Plan"

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_no', 'payment', 'total', 'stripe_invoice_url', 'created_at')
    search_fields = ('invoice_no', 'payment__company__name')

@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'status', 'processed_at')
    list_filter = ('status', 'event_type')
    search_fields = ('event_id', 'event_type')

@admin.register(SubscriptionAuditLog)
class SubscriptionAuditLogAdmin(admin.ModelAdmin):
    list_display = ('company', 'get_user', 'action', 'timestamp')
    list_filter = ('action',)
    search_fields = ('company__name', 'company__owner__email', 'company__owner__username')

    def get_user(self, obj):
        return obj.company.owner.email if obj.company and hasattr(obj.company, 'owner') and obj.company.owner else '-'
    get_user.short_description = 'User (Owner)'
    get_user.admin_order_field = 'company__owner__email'
