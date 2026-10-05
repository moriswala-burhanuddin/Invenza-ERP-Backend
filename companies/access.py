"""
Access control helpers for the ERP desktop app.

Decides whether a company is allowed to sign in based on its trial /
subscription state. The rules intentionally mirror ERPCredentialsView so that
login, the in-app SubscriptionGuard and the portal all agree with each other.

Only *clearly* lapsed accounts are blocked:
  * a free trial whose 7 days are over (and that never converted to a paid plan)
  * a subscription that is EXPIRED / CANCELLED / SUSPENDED

Active, grace-period and in-trial companies are never blocked here.
"""

PRICING_URL = 'https://invenza.uk/pricing'

TRIAL_EXPIRED = 'TRIAL_EXPIRED'
SUBSCRIPTION_EXPIRED = 'SUBSCRIPTION_EXPIRED'

_BLOCKING_SUBSCRIPTION_STATUSES = ('expired', 'cancelled', 'suspended')


def get_access_block(company):
    """
    Returns None when the company may sign in, otherwise a dict:
        {'code': 'TRIAL_EXPIRED' | 'SUBSCRIPTION_EXPIRED', 'detail': '<message>', 'action_url': '<url>'}
    """
    subscription = None
    try:
        subscription = company.subscription
    except Exception:
        # No Subscription row yet (legacy / brand-new companies) -> fall back to company fields
        subscription = None

    if subscription is not None and subscription.status:
        sub_status = subscription.status.lower()
    else:
        sub_status = (company.subscription_status or '').lower()

    # Paid / grace accounts are always allowed through.
    if sub_status in ('active', 'grace'):
        return None

    if sub_status == 'trial':
        if company.trial_days_left <= 0:
            return _trial_expired()
        return None

    if sub_status in _BLOCKING_SUBSCRIPTION_STATUSES:
        # A company that never paid and is flagged expired is a lapsed trial.
        ever_paid = bool(
            subscription is not None
            and (subscription.stripe_subscription_id or subscription.last_payment_id)
        )
        if ever_paid:
            return _subscription_expired()
        return _trial_expired()

    # past_due / incomplete / unknown -> let the in-app guard decide, as before.
    return None


def _trial_expired():
    return {
        'code': TRIAL_EXPIRED,
        'detail': (
            'Your 7-day free trial has ended. Subscribe to a plan to regain access '
            'to your Invenza workspace. Your data is safe and will be available '
            'as soon as your subscription is active.'
        ),
        'action_url': PRICING_URL,
    }


def _subscription_expired():
    return {
        'code': SUBSCRIPTION_EXPIRED,
        'detail': (
            'Your Invenza subscription has expired. Renew your plan to restore access '
            'to your workspace. Your data is safe and will be available as soon as '
            'your subscription is renewed.'
        ),
        'action_url': PRICING_URL,
    }
