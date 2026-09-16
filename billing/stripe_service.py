"""
Stripe Service Layer
====================
Encapsulates all Stripe API interactions for subscription billing.
Handles customer management, checkout sessions, customer portal,
subscription lifecycle, and webhook event processing.
"""

import stripe
import logging
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timezone as dt_timezone

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# ─────────────────────────────────────────────
# Customer Management
# ─────────────────────────────────────────────

def get_or_create_stripe_customer(company, user):
    """
    Returns a Stripe Customer ID. Creates one if it doesn't exist.
    Stores the ID on both the Company and Subscription models.
    """
    # Check if company already has a Stripe customer ID
    if company.stripe_customer_id:
        try:
            customer = stripe.Customer.retrieve(company.stripe_customer_id)
            if not getattr(customer, 'deleted', False):
                return company.stripe_customer_id
        except stripe.error.InvalidRequestError:
            logger.warning(f"Stripe customer {company.stripe_customer_id} not found, creating new one.")

    # Create new Stripe customer
    customer = stripe.Customer.create(
        email=user.email,
        name=company.name,
        metadata={
            'company_id': str(company.id),
            'company_name': company.name,
            'user_id': str(user.id),
        }
    )

    # Save to company
    company.stripe_customer_id = customer.id
    company.save(update_fields=['stripe_customer_id'])

    # Also save to subscription if it exists
    try:
        subscription = company.subscription
        subscription.stripe_customer_id = customer.id
        subscription.save(update_fields=['stripe_customer_id'])
    except Exception:
        pass

    logger.info(f"Created Stripe customer {customer.id} for company {company.name}")
    return customer.id


# ─────────────────────────────────────────────
# Checkout Session
# ─────────────────────────────────────────────

def create_checkout_session(company, user, plan, billing_interval='month'):
    """
    Creates a Stripe Checkout Session for a subscription.
    Returns the session object with the checkout URL.
    
    Args:
        company: Company model instance
        user: User model instance
        plan: Plan model instance
        billing_interval: 'month' or 'year'
    """
    customer_id = get_or_create_stripe_customer(company, user)
    
    # Determine the correct Stripe Price ID from the Plan
    price_id = plan.stripe_price_id
    if not price_id:
        raise ValueError(f"Stripe Price ID is not configured for the plan '{plan.name}'.")

    # Build the session
    session_params = {
        'customer': customer_id,
        'payment_method_types': ['card'],
        'line_items': [{
            'price': price_id,
            'quantity': 1,
        }],
        'mode': 'subscription',
        'success_url': f"{settings.FRONTEND_URL}/checkout-success?session_id={{CHECKOUT_SESSION_ID}}",
        'cancel_url': f"{settings.FRONTEND_URL}/pricing",
        'metadata': {
            'company_id': str(company.id),
            'plan_id': str(plan.id),
            'billing_interval': billing_interval,
        },
        'subscription_data': {
            'metadata': {
                'company_id': str(company.id),
                'plan_id': str(plan.id),
            },
        },
        'allow_promotion_codes': True,
    }

    # Trial period is intentionally omitted here. 
    # If the user clicks pay, we charge them immediately for the plan (no free Stripe trial).

    session = stripe.checkout.Session.create(**session_params)
    
    logger.info(f"Created Checkout Session {session.id} for company {company.name}, plan {plan.name} ({billing_interval})")
    return session


# ─────────────────────────────────────────────
# Customer Portal
# ─────────────────────────────────────────────

def create_customer_portal_session(company):
    """
    Creates a Stripe Customer Portal session.
    The portal lets users manage payment methods, view invoices, and cancel subscriptions.
    """
    if not company.stripe_customer_id:
        raise ValueError("Company does not have a Stripe customer ID.")

    session = stripe.billing_portal.Session.create(
        customer=company.stripe_customer_id,
        return_url=f"{settings.FRONTEND_URL}/dashboard",
    )

    return session


# ─────────────────────────────────────────────
# Subscription Lifecycle
# ─────────────────────────────────────────────

def cancel_subscription(stripe_subscription_id, immediately=False):
    """
    Cancels a Stripe subscription.
    By default, cancels at the end of the current billing period.
    """
    if immediately:
        subscription = stripe.Subscription.cancel(stripe_subscription_id)
    else:
        subscription = stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True,
        )
    
    logger.info(f"Cancelled subscription {stripe_subscription_id} (immediately={immediately})")
    return subscription


def resume_subscription(stripe_subscription_id):
    """
    Resumes a subscription that was set to cancel at period end.
    """
    subscription = stripe.Subscription.modify(
        stripe_subscription_id,
        cancel_at_period_end=False,
    )
    
    logger.info(f"Resumed subscription {stripe_subscription_id}")
    return subscription


def change_subscription_plan(stripe_subscription_id, new_price_id):
    """
    Changes the subscription to a different plan/price.
    Stripe handles proration automatically.
    """
    subscription = stripe.Subscription.retrieve(stripe_subscription_id)
    
    updated_subscription = stripe.Subscription.modify(
        stripe_subscription_id,
        items=[{
            'id': subscription['items']['data'][0]['id'],
            'price': new_price_id,
        }],
        proration_behavior='create_prorations',
    )
    
    logger.info(f"Changed subscription {stripe_subscription_id} to price {new_price_id}")
    return updated_subscription


def retrieve_subscription(stripe_subscription_id):
    """
    Retrieves the latest subscription state from Stripe.
    """
    return stripe.Subscription.retrieve(stripe_subscription_id)


# ─────────────────────────────────────────────
# Checkout Session Retrieval
# ─────────────────────────────────────────────

def retrieve_checkout_session(session_id):
    """
    Retrieves a completed Checkout Session with line items and subscription details.
    """
    session = stripe.checkout.Session.retrieve(
        session_id,
        expand=['subscription', 'line_items', 'customer'],
    )
    return session


# ─────────────────────────────────────────────
# Webhook Helpers
# ─────────────────────────────────────────────

def construct_webhook_event(payload, sig_header):
    """
    Constructs and verifies a Stripe webhook event from the raw payload.
    Raises stripe.error.SignatureVerificationError if invalid.
    """
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
    return event


def sync_subscription_from_stripe(stripe_subscription_id):
    """
    Pulls the latest subscription state from Stripe and returns a normalized dict.
    Used for both webhook processing and manual sync.
    
    Note: Some fields (current_period_start, current_period_end) may not exist
    on subscriptions in certain states (trialing, incomplete). We handle this
    gracefully with safe access.
    """
    sub = stripe.Subscription.retrieve(stripe_subscription_id)
    
    # Safely extract timestamps — they may not exist on top level for some Stripe setups
    period_start_ts = getattr(sub, 'current_period_start', None)
    period_end_ts = getattr(sub, 'current_period_end', None)
    trial_end_ts = getattr(sub, 'trial_end', None)
    
    # Fallback to extracting from the first subscription item
    price_id = None
    try:
        items_data = sub['items']['data']
        if items_data:
            item = items_data[0]
            price_id = item['price']['id']
            # Fallback for period dates if missing from top-level (happens with some Stripe configs/API versions)
            if not period_start_ts:
                period_start_ts = getattr(item, 'current_period_start', None)
            if not period_end_ts:
                period_end_ts = getattr(item, 'current_period_end', None)
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    
    return {
        'stripe_subscription_id': sub.id,
        'stripe_customer_id': sub.customer if isinstance(sub.customer, str) else sub.customer.id,
        'status': _map_stripe_status(sub.status),
        'current_period_start': datetime.fromtimestamp(period_start_ts, tz=dt_timezone.utc) if period_start_ts else None,
        'current_period_end': datetime.fromtimestamp(period_end_ts or trial_end_ts, tz=dt_timezone.utc) if (period_end_ts or trial_end_ts) else None,
        'cancel_at_period_end': getattr(sub, 'cancel_at_period_end', False),
        'price_id': price_id,
        'trial_end': datetime.fromtimestamp(trial_end_ts, tz=dt_timezone.utc) if trial_end_ts else None,
    }


def _map_stripe_status(stripe_status):
    """
    Maps Stripe subscription statuses to our internal status choices.
    Stripe statuses: active, past_due, unpaid, canceled, incomplete, incomplete_expired, trialing, paused
    """
    status_map = {
        'active': 'ACTIVE',
        'trialing': 'TRIAL',
        'past_due': 'PAST_DUE',
        'canceled': 'CANCELLED',
        'unpaid': 'SUSPENDED',
        'incomplete': 'INCOMPLETE',
        'incomplete_expired': 'EXPIRED',
        'paused': 'SUSPENDED',
    }
    return status_map.get(stripe_status, 'EXPIRED')
