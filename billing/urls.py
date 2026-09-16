from django.urls import path
from .views import (
    PlanListView,
    CreateCheckoutSessionView,
    CheckoutSuccessView,
    SubscriptionStatusView,
    CustomerPortalView,
    CancelSubscriptionView,
    ResumeSubscriptionView,
    ChangeSubscriptionView,
    StripeWebhookView,
    WebhookView,
)

urlpatterns = [
    # Plan browsing
    path('plans/', PlanListView.as_view(), name='plans_list'),

    # Stripe Checkout flow
    path('create-checkout-session/', CreateCheckoutSessionView.as_view(), name='create_checkout_session'),
    path('checkout-success/', CheckoutSuccessView.as_view(), name='checkout_success'),

    # Subscription management
    path('subscription-status/', SubscriptionStatusView.as_view(), name='subscription_status'),
    path('customer-portal/', CustomerPortalView.as_view(), name='customer_portal'),
    path('cancel-subscription/', CancelSubscriptionView.as_view(), name='cancel_subscription'),
    path('resume-subscription/', ResumeSubscriptionView.as_view(), name='resume_subscription'),
    path('change-plan/', ChangeSubscriptionView.as_view(), name='change_plan'),

    # Stripe Webhook
    path('stripe-webhook/', StripeWebhookView.as_view(), name='stripe_webhook'),

    # Legacy Razorpay webhook (deprecated, kept for backward compatibility)
    path('webhook/', WebhookView.as_view(), name='razorpay_webhook'),
]
