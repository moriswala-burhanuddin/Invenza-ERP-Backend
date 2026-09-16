import json
import logging
import stripe
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Subscription, Payment, Invoice, WebhookEvent, SubscriptionAuditLog, Plan
from .serializers import PlanSerializer, SubscriptionStatusSerializer
from companies.models import Company
from . import stripe_service

logger = logging.getLogger(__name__)


def _get(obj, key, default=None):
    """Safely get a value from either a dict or a Stripe object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class PlanListView(APIView):
    """Returns all active plans, grouped for frontend display."""
    permission_classes = []

    def get(self, request):
        plans = Plan.objects.filter(is_active=True).order_by('monthly_price')
        serializer = PlanSerializer(plans, many=True)
        return Response(serializer.data)


class CreateCheckoutSessionView(APIView):
    """Creates a Stripe Checkout Session and returns the URL for redirect."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        billing_interval = 'year'  # Forced to yearly subscription

        if not plan_id:
            return Response({'error': 'Plan ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)

        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            session = stripe_service.create_checkout_session(
                company=company,
                user=request.user,
                plan=plan,
                billing_interval=billing_interval,
            )

            # Audit log
            SubscriptionAuditLog.objects.create(
                company=company,
                action='CHECKOUT_SESSION_CREATED',
                details={
                    'session_id': session.id,
                    'plan_id': plan_id,
                    'billing_interval': billing_interval,
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return Response({
                'checkout_url': session.url,
                'session_id': session.id,
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating checkout session: {e}")
            return Response({'error': 'Failed to create checkout session'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckoutSuccessView(APIView):
    """
    Called after Stripe redirects user back on successful checkout.
    Verifies the session and syncs subscription state.
    
    This endpoint is designed to be called multiple times safely (idempotent).
    The frontend may poll this endpoint until the subscription is confirmed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({'error': 'Session ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        # Fast path: if subscription is already synced (e.g. by webhook), just return it
        try:
            sub = company.subscription
            if sub.stripe_subscription_id and sub.status in ('ACTIVE', 'TRIAL'):
                return Response({
                    'status': 'active',
                    'plan_name': sub.plan.name if sub.plan else 'Invenza ERP',
                    'next_billing_date': sub.current_period_end.isoformat() if sub.current_period_end else None,
                    'billing_interval': sub.billing_interval,
                })
        except Subscription.DoesNotExist:
            pass

        # Slow path: fetch session from Stripe and sync
        try:
            session = stripe_service.retrieve_checkout_session(session_id)
            logger.info(f"Checkout session {session_id}: payment_status={session.payment_status}, subscription={getattr(session, 'subscription', None)}")

            if session.payment_status not in ('paid', 'no_payment_required'):
                return Response({
                    'status': 'pending',
                    'message': 'Payment is still being processed. Please wait...',
                })

            # Extract the subscription ID (could be a string or expanded object)
            stripe_sub = session.subscription
            stripe_sub_id = None
            if stripe_sub:
                if isinstance(stripe_sub, str):
                    stripe_sub_id = stripe_sub
                else:
                    stripe_sub_id = getattr(stripe_sub, 'id', None)

            if not stripe_sub_id:
                # Subscription hasn't been created yet — tell frontend to retry
                logger.warning(f"Checkout session {session_id} paid but no subscription ID yet")
                return Response({
                    'status': 'pending',
                    'message': 'Subscription is being provisioned. Please wait...',
                })

            # Sync the subscription from Stripe into our database
            with transaction.atomic():
                _sync_subscription_from_stripe_id(company, session, stripe_sub_id)

            # Refresh from DB
            company.refresh_from_db()
            sub = company.subscription

            return Response({
                'status': 'active',
                'plan_name': sub.plan.name if sub.plan else 'Invenza ERP',
                'next_billing_date': sub.current_period_end.isoformat() if sub.current_period_end else None,
                'billing_interval': sub.billing_interval,
            })

        except stripe.error.InvalidRequestError as e:
            logger.error(f"Invalid Stripe session {session_id}: {e}")
            return Response({'error': 'Invalid checkout session. It may have expired.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error processing checkout success for session {session_id}: {e}", exc_info=True)
            return Response({'error': 'Payment verification is taking longer than expected. Please try refreshing the page.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubscriptionStatusView(APIView):
    """Returns the current subscription status for the authenticated user's company."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            subscription = company.subscription
        except Subscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

        # Get payment history
        payments = Payment.objects.filter(
            company=company,
            status='CAPTURED'
        ).order_by('-created_at')[:10]

        invoices = Invoice.objects.filter(
            payment__company=company
        ).order_by('-created_at')[:10]

        data = {
            'subscription': {
                'status': subscription.status,
                'plan_name': subscription.plan.name if subscription.plan else None,
                'plan_id': subscription.plan.id if subscription.plan else None,
                'monthly_price': str(subscription.plan.monthly_price) if subscription.plan else None,
                'billing_interval': subscription.billing_interval,
                'current_period_start': subscription.current_period_start.isoformat() if subscription.current_period_start else None,
                'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
                'cancel_at_period_end': subscription.cancel_at_period_end,
                'auto_renew': subscription.auto_renew,
                'is_active': subscription.is_subscription_active,
                'stripe_subscription_id': subscription.stripe_subscription_id,
            },
            'payments': [{
                'id': p.id,
                'amount': p.amount,
                'currency': p.currency,
                'status': p.status,
                'payment_method': p.payment_method,
                'created_at': p.created_at.isoformat(),
            } for p in payments],
            'invoices': [{
                'id': inv.id,
                'invoice_no': inv.invoice_no,
                'total': str(inv.total),
                'stripe_invoice_url': inv.stripe_invoice_url,
                'created_at': inv.created_at.isoformat(),
            } for inv in invoices],
        }

        return Response(data)


class CustomerPortalView(APIView):
    """Creates a Stripe Customer Portal session for managing billing."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        if not company.stripe_customer_id:
            return Response({'error': 'No billing account found. Please subscribe first.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = stripe_service.create_customer_portal_session(company)
            return Response({'portal_url': session.url})
        except Exception as e:
            logger.error(f"Error creating customer portal session: {e}")
            return Response({'error': 'Failed to create billing portal session'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CancelSubscriptionView(APIView):
    """Cancels the current subscription at end of billing period."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            subscription = company.subscription
        except Subscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

        if not subscription.stripe_subscription_id:
            return Response({'error': 'No active Stripe subscription found'}, status=status.HTTP_400_BAD_REQUEST)

        immediately = request.data.get('immediately', False)

        try:
            stripe_service.cancel_subscription(
                subscription.stripe_subscription_id,
                immediately=immediately
            )

            if immediately:
                subscription.status = 'CANCELLED'
                subscription.is_active = False
                subscription.auto_renew = False
            else:
                subscription.cancel_at_period_end = True
                subscription.auto_renew = False

            subscription.save()

            # Update legacy company fields
            if immediately:
                company.subscription_status = 'expired'
                company.save(update_fields=['subscription_status'])

            SubscriptionAuditLog.objects.create(
                company=company,
                action='SUBSCRIPTION_CANCELLED',
                details={
                    'immediately': immediately,
                    'stripe_subscription_id': subscription.stripe_subscription_id,
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return Response({
                'message': 'Subscription cancelled' if immediately else 'Subscription will cancel at the end of the current billing period',
                'cancel_at_period_end': subscription.cancel_at_period_end,
                'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            })
        except Exception as e:
            logger.error(f"Error cancelling subscription: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResumeSubscriptionView(APIView):
    """Resumes a subscription that was set to cancel at period end."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            subscription = company.subscription
        except Subscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

        if not subscription.stripe_subscription_id:
            return Response({'error': 'No Stripe subscription found'}, status=status.HTTP_400_BAD_REQUEST)

        if not subscription.cancel_at_period_end:
            return Response({'error': 'Subscription is not set to cancel'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            stripe_service.resume_subscription(subscription.stripe_subscription_id)
            subscription.cancel_at_period_end = False
            subscription.auto_renew = True
            subscription.save()

            SubscriptionAuditLog.objects.create(
                company=company,
                action='SUBSCRIPTION_RESUMED',
                details={'stripe_subscription_id': subscription.stripe_subscription_id},
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return Response({'message': 'Subscription resumed successfully'})
        except Exception as e:
            logger.error(f"Error resuming subscription: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChangeSubscriptionView(APIView):
    """Upgrades or downgrades the subscription to a different plan."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        new_plan_id = request.data.get('plan_id')
        if not new_plan_id:
            return Response({'error': 'New plan ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        company = request.user.owned_companies.first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            subscription = company.subscription
        except Subscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

        if not subscription.stripe_subscription_id:
            return Response({'error': 'No active Stripe subscription. Please subscribe first.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_plan = Plan.objects.get(id=new_plan_id, is_active=True)
        except Plan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)

        if not new_plan.stripe_price_id:
            return Response({'error': 'Plan is not configured for Stripe billing'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_sub = stripe_service.change_subscription_plan(
                subscription.stripe_subscription_id,
                new_plan.stripe_price_id
            )

            # Update local subscription
            subscription.plan = new_plan
            subscription.billing_interval = new_plan.billing_interval
            subscription.save()

            SubscriptionAuditLog.objects.create(
                company=company,
                action='PLAN_CHANGED',
                details={
                    'new_plan_id': new_plan_id,
                    'new_plan_name': new_plan.name,
                    'stripe_subscription_id': subscription.stripe_subscription_id,
                },
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return Response({
                'message': f'Plan changed to {new_plan.name}',
                'plan_name': new_plan.name,
                'monthly_price': str(new_plan.monthly_price),
            })
        except Exception as e:
            logger.error(f"Error changing subscription plan: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StripeWebhookView(APIView):
    """
    Receives Stripe webhook events.
    Handles subscription lifecycle, payment success/failure, and invoice events.
    
    In DEBUG mode with no STRIPE_WEBHOOK_SECRET configured, signature
    verification is skipped to allow local development/testing.
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

        # Verify webhook signature (skip in dev if no secret configured)
        if webhook_secret:
            if not sig_header:
                return Response({'error': 'Missing Stripe signature'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                event = stripe_service.construct_webhook_event(payload, sig_header)
            except Exception as e:
                logger.error(f"Webhook signature verification failed: {e}")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        elif settings.DEBUG:
            # Dev mode: parse the payload directly without signature verification
            logger.warning("STRIPE_WEBHOOK_SECRET is not set — skipping signature verification (DEBUG mode)")
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                return Response({'error': 'Invalid JSON payload'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Production without a webhook secret is a misconfiguration
            logger.error("STRIPE_WEBHOOK_SECRET is not configured! Webhooks will not work in production.")
            return Response({'error': 'Webhook not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        event_id = event['id']
        event_type = event['type']

        # Idempotency check
        if WebhookEvent.objects.filter(event_id=event_id).exists():
            return Response({'message': 'Already processed'})

        # Store webhook event
        WebhookEvent.objects.create(
            event_id=event_id,
            event_type=event_type,
            payload=event['data'],
            signature=sig_header[:255] if sig_header else None,
        )

        # Route event to handler
        try:
            if event_type == 'checkout.session.completed':
                self._handle_checkout_completed(event['data']['object'])
            elif event_type == 'invoice.paid':
                self._handle_invoice_paid(event['data']['object'])
            elif event_type == 'invoice.payment_failed':
                self._handle_invoice_payment_failed(event['data']['object'])
            elif event_type == 'customer.subscription.updated':
                self._handle_subscription_updated(event['data']['object'])
            elif event_type == 'customer.subscription.deleted':
                self._handle_subscription_deleted(event['data']['object'])
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
        except Exception as e:
            logger.error(f"Error processing webhook {event_type}: {e}", exc_info=True)
            # Still return 200 to prevent Stripe retries for processing errors
            return Response({'status': 'error', 'message': str(e)})

        return Response({'status': 'ok'})

    def _handle_checkout_completed(self, session):
        """Process a completed checkout session."""
        metadata = _get(session, 'metadata', {}) or {}
        if not isinstance(metadata, dict) and hasattr(metadata, 'to_dict'):
            metadata = metadata.to_dict()
            
        company_id = metadata.get('company_id') if isinstance(metadata, dict) else None
        plan_id = metadata.get('plan_id') if isinstance(metadata, dict) else None
        billing_interval = metadata.get('billing_interval', 'year') if isinstance(metadata, dict) else 'year'
        
        stripe_subscription_id = _get(session, 'subscription', None)
        stripe_customer_id = _get(session, 'customer', None)

        if not company_id or not plan_id:
            logger.warning(f"Checkout session missing metadata: {_get(session, 'id', 'unknown')}")
            return

        try:
            company = Company.objects.get(id=int(company_id))
        except Company.DoesNotExist:
            logger.error(f"Company {company_id} not found for checkout session")
            return

        # Sync subscription from Stripe
        stripe_sub_data = stripe_service.sync_subscription_from_stripe(stripe_subscription_id)

        with transaction.atomic():
            # Get or create subscription
            subscription, _ = Subscription.objects.get_or_create(company=company)

            # Get plan
            plan = None
            if plan_id:
                try:
                    plan = Plan.objects.get(id=int(plan_id))
                except Plan.DoesNotExist:
                    pass

            # Update subscription
            subscription.stripe_subscription_id = stripe_subscription_id
            subscription.stripe_customer_id = stripe_customer_id
            subscription.status = stripe_sub_data['status']
            subscription.current_period_start = stripe_sub_data['current_period_start']
            subscription.current_period_end = stripe_sub_data['current_period_end']
            subscription.cancel_at_period_end = stripe_sub_data['cancel_at_period_end']
            subscription.expiry_date = stripe_sub_data['current_period_end']
            subscription.is_active = True
            subscription.auto_renew = True
            subscription.billing_interval = billing_interval
            if plan:
                subscription.plan = plan
            subscription.save()

            # Update company
            company.stripe_customer_id = stripe_customer_id
            company.subscription_status = 'active' if subscription.status in ('ACTIVE', 'TRIAL') else subscription.status.lower()
            company.expiry_date = subscription.current_period_end
            company.save()

            # Audit log
            SubscriptionAuditLog.objects.create(
                company=company,
                action='CHECKOUT_COMPLETED',
                details={
                    'stripe_subscription_id': stripe_subscription_id,
                    'plan_id': plan_id,
                    'billing_interval': billing_interval,
                    'status': subscription.status,
                }
            )

            logger.info(f"Checkout completed for company {company.name}, subscription {stripe_subscription_id}")

    def _handle_invoice_paid(self, invoice_data):
        """Process a successful payment (initial or recurring autopay)."""
        stripe_subscription_id = _get(invoice_data, 'subscription', None)
        stripe_customer_id = _get(invoice_data, 'customer', None)
        amount_paid = _get(invoice_data, 'amount_paid', 0)
        currency = _get(invoice_data, 'currency', 'gbp')
        if currency:
            currency = currency.upper()
        stripe_invoice_id = _get(invoice_data, 'id', None)
        hosted_invoice_url = _get(invoice_data, 'hosted_invoice_url', None)
        payment_intent_id = _get(invoice_data, 'payment_intent', None)

        if not stripe_subscription_id:
            return

        # Find the subscription
        try:
            subscription = Subscription.objects.get(stripe_subscription_id=stripe_subscription_id)
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription not found for invoice.paid: {stripe_subscription_id}")
            return

        company = subscription.company

        with transaction.atomic():
            # Sync subscription state from Stripe
            stripe_sub_data = stripe_service.sync_subscription_from_stripe(stripe_subscription_id)

            subscription.status = stripe_sub_data['status']
            subscription.current_period_start = stripe_sub_data['current_period_start']
            subscription.current_period_end = stripe_sub_data['current_period_end']
            subscription.cancel_at_period_end = stripe_sub_data['cancel_at_period_end']
            subscription.expiry_date = stripe_sub_data['current_period_end']
            subscription.is_active = True
            subscription.save()

            # Update company legacy fields
            company.subscription_status = 'active'
            company.expiry_date = subscription.current_period_end
            company.save()

            # Create Payment record
            payment = Payment.objects.create(
                company=company,
                user=company.owner,
                amount=amount_paid,
                currency=currency,
                plan_id=subscription.plan.id if subscription.plan else None,
                status='CAPTURED',
                payment_method='stripe',
                stripe_payment_intent_id=payment_intent_id,
                stripe_invoice_id=stripe_invoice_id,
                verified_at=timezone.now(),
            )

            subscription.last_payment = payment
            subscription.save(update_fields=['last_payment'])

            # Create Invoice record
            invoice_no = f"INV-{timezone.now().year}-{payment.id:06d}"
            Invoice.objects.create(
                invoice_no=invoice_no,
                payment=payment,
                subtotal=amount_paid / 100.0,
                tax=0.0,
                total=amount_paid / 100.0,
                stripe_invoice_url=hosted_invoice_url,
            )

            # Audit log
            SubscriptionAuditLog.objects.create(
                company=company,
                action='PAYMENT_CAPTURED',
                details={
                    'stripe_invoice_id': stripe_invoice_id,
                    'amount': amount_paid,
                    'currency': currency,
                }
            )

            # Send payment success email
            self._send_payment_email(company, payment, subscription)

            logger.info(f"Invoice paid for company {company.name}: {currency} {amount_paid/100:.2f}")

    def _handle_invoice_payment_failed(self, invoice_data):
        """Process a failed payment attempt (autopay failure)."""
        stripe_subscription_id = _get(invoice_data, 'subscription', None)
        stripe_invoice_id = _get(invoice_data, 'id', None)
        attempt_count = _get(invoice_data, 'attempt_count', 0)

        if not stripe_subscription_id:
            return

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=stripe_subscription_id)
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription not found for payment failure: {stripe_subscription_id}")
            return

        company = subscription.company

        with transaction.atomic():
            # Set grace/past_due status
            if subscription.status == 'ACTIVE':
                subscription.status = 'PAST_DUE'
                subscription.save()

            # Create a failed payment record
            Payment.objects.create(
                company=company,
                user=company.owner,
                amount=_get(invoice_data, 'amount_due', 0),
                currency=_get(invoice_data, 'currency', 'gbp').upper() if _get(invoice_data, 'currency', None) else 'GBP',
                plan_id=subscription.plan.id if subscription.plan else None,
                status='FAILED',
                payment_method='stripe',
                stripe_invoice_id=stripe_invoice_id,
            )

            # Audit log
            SubscriptionAuditLog.objects.create(
                company=company,
                action='PAYMENT_FAILED',
                details={
                    'stripe_invoice_id': stripe_invoice_id,
                    'attempt_count': attempt_count,
                }
            )

            # Send failure notification email
            self._send_payment_failed_email(company, subscription)

            logger.warning(f"Payment failed for company {company.name} (attempt {attempt_count})")

    def _handle_subscription_updated(self, sub_data):
        """Process subscription updates (plan change, status change, etc.)."""
        stripe_subscription_id = _get(sub_data, 'id', None)

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=stripe_subscription_id)
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription not found for update: {stripe_subscription_id}")
            return

        # Sync from Stripe
        stripe_sub_data = stripe_service.sync_subscription_from_stripe(stripe_subscription_id)

        was_cancelling = subscription.cancel_at_period_end

        subscription.status = stripe_sub_data['status']
        subscription.current_period_start = stripe_sub_data['current_period_start']
        subscription.current_period_end = stripe_sub_data['current_period_end']
        subscription.cancel_at_period_end = stripe_sub_data['cancel_at_period_end']
        subscription.expiry_date = stripe_sub_data['current_period_end']

        if not was_cancelling and subscription.cancel_at_period_end:
            # They just set it to cancel at the end of the billing period
            self._send_subscription_cancelled_period_end_email(company, subscription)

        # Update plan if price changed
        if stripe_sub_data['price_id']:
            try:
                new_plan = Plan.objects.get(stripe_price_id=stripe_sub_data['price_id'])
                subscription.plan = new_plan
            except Plan.DoesNotExist:
                pass

        subscription.save()

        # Update company legacy fields
        company = subscription.company
        company.subscription_status = 'active' if subscription.status in ('ACTIVE', 'TRIAL') else subscription.status.lower()
        company.expiry_date = subscription.current_period_end
        company.save()

        logger.info(f"Subscription updated for company {company.name}: {subscription.status}")

    def _handle_subscription_deleted(self, sub_data):
        """Process subscription cancellation/deletion."""
        stripe_subscription_id = _get(sub_data, 'id', None)

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=stripe_subscription_id)
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription not found for deletion: {stripe_subscription_id}")
            return

        company = subscription.company

        subscription.status = 'CANCELLED'
        subscription.is_active = False
        subscription.auto_renew = False
        subscription.save()

        # Update company legacy fields
        company.subscription_status = 'expired'
        company.save(update_fields=['subscription_status'])

        SubscriptionAuditLog.objects.create(
            company=company,
            action='SUBSCRIPTION_DELETED',
            details={'stripe_subscription_id': stripe_subscription_id}
        )

        # Send cancellation email
        self._send_subscription_cancelled_email(company)

        logger.info(f"Subscription deleted for company {company.name}")

    def _send_payment_email(self, company, payment, subscription):
        """Sends payment success email with invoice."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        from datetime import datetime

        try:
            plan_name = subscription.plan.name if subscription.plan else "Enterprise Plan"
            context = {
                'company_name': company.name,
                'user_email': company.owner.email,
                'plan_name': plan_name,
                'invoice_no': f"INV-{timezone.now().year}-{payment.id:06d}",
                'amount': f"{payment.amount / 100.0:.2f}",
                'currency': payment.currency,
                'expiry_date': subscription.current_period_end.strftime("%B %d, %Y") if subscription.current_period_end else "N/A",
                'current_date': timezone.now().strftime("%B %d, %Y"),
                'dashboard_url': f"{settings.FRONTEND_URL}/dashboard",
                'current_year': datetime.now().year,
            }

            html_content = render_to_string('billing/email/payment_success.html', context)
            text_content = strip_tags(html_content)

            admin_emails = [admin[1] for admin in settings.ADMINS] if hasattr(settings, 'ADMINS') else []

            email = EmailMultiAlternatives(
                subject=f'Payment Receipt & Invoice - {company.name}',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[company.owner.email],
                bcc=admin_emails,
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=True)
        except Exception as e:
            logger.error(f"Error sending payment email: {e}")

    def _send_payment_failed_email(self, company, subscription):
        """Sends payment failure notification email."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags

        try:
            context = {
                'company_name': company.name,
                'plan_name': subscription.plan.name if subscription.plan else "your plan",
                'update_payment_url': f"{settings.FRONTEND_URL}/dashboard",
                'current_year': timezone.now().year,
            }

            html_content = render_to_string('billing/email/payment_failed.html', context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject='Action Required: Payment Failed (Grace Period Started) - Invenza ERP',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[company.owner.email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=True)
        except Exception as e:
            logger.error(f"Error sending payment failed email: {e}")

    def _send_subscription_cancelled_email(self, company):
        """Sends immediate subscription cancellation email."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags

        try:
            context = {
                'company_name': company.name,
                'resubscribe_url': f"{settings.FRONTEND_URL}/pricing",
                'current_year': timezone.now().year,
            }

            html_content = render_to_string('billing/email/subscription_cancelled.html', context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject='Subscription Terminated - Invenza ERP',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[company.owner.email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=True)
        except Exception as e:
            logger.error(f"Error sending cancellation email: {e}")

    def _send_subscription_cancelled_period_end_email(self, company, subscription):
        """Sends email when subscription is set to cancel at end of year."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags

        try:
            context = {
                'company_name': company.name,
                'end_date': subscription.current_period_end.strftime("%B %d, %Y") if subscription.current_period_end else "the end of your billing cycle",
                'current_year': timezone.now().year,
            }

            html_content = render_to_string('billing/email/subscription_cancelled_period_end.html', context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject='Subscription Cancellation Confirmed - Invenza ERP',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[company.owner.email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=True)
        except Exception as e:
            logger.error(f"Error sending end of period cancellation email: {e}")


# ─────────────────────────────────────────────
# Legacy Razorpay Webhook (kept for backward compatibility)
# ─────────────────────────────────────────────

class WebhookView(APIView):
    """Legacy Razorpay webhook. Kept to avoid breaking existing webhook registrations."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        logger.info("Received legacy Razorpay webhook call — Razorpay is deprecated, ignoring.")
        return Response({'status': 'ok', 'message': 'Razorpay webhooks are deprecated. Migrate to Stripe.'})


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────

def _sync_subscription_from_stripe_id(company, session, stripe_sub_id):
    """
    Syncs subscription state by fetching the latest data directly from Stripe
    using the subscription ID. This is the single source of truth and avoids
    issues with expanded objects having inconsistent or missing fields.
    """
    # Extract metadata from the checkout session
    metadata = getattr(session, 'metadata', {}) or {}
    if not isinstance(metadata, dict) and hasattr(metadata, 'to_dict'):
        metadata = metadata.to_dict()

    plan_id = metadata.get('plan_id') if isinstance(metadata, dict) else None
    billing_interval = metadata.get('billing_interval', 'year') if isinstance(metadata, dict) else 'year'

    # Get local plan
    plan = None
    if plan_id:
        try:
            plan = Plan.objects.get(id=int(plan_id))
        except (Plan.DoesNotExist, ValueError, TypeError):
            logger.warning(f"Plan {plan_id} not found during sync")

    # Fetch fresh subscription data from Stripe API (the source of truth)
    stripe_sub_data = stripe_service.sync_subscription_from_stripe(stripe_sub_id)

    # Get or create local subscription
    subscription, created = Subscription.objects.get_or_create(company=company)

    # Update subscription fields
    subscription.stripe_subscription_id = stripe_sub_data['stripe_subscription_id']
    subscription.stripe_customer_id = stripe_sub_data['stripe_customer_id']
    subscription.status = stripe_sub_data['status']
    subscription.current_period_start = stripe_sub_data.get('current_period_start')
    subscription.current_period_end = stripe_sub_data.get('current_period_end')
    subscription.cancel_at_period_end = stripe_sub_data.get('cancel_at_period_end', False)
    subscription.expiry_date = stripe_sub_data.get('current_period_end')
    subscription.is_active = True
    subscription.auto_renew = True
    subscription.billing_interval = billing_interval
    if plan:
        subscription.plan = plan
    subscription.save()

    # Update company fields
    company.stripe_customer_id = stripe_sub_data['stripe_customer_id']
    company.subscription_status = 'active' if subscription.status in ('ACTIVE', 'TRIAL') else subscription.status.lower()
    company.expiry_date = subscription.current_period_end
    company.save()

    # Audit log
    SubscriptionAuditLog.objects.create(
        company=company,
        action='CHECKOUT_SUCCESS_SYNCED',
        details={
            'stripe_subscription_id': stripe_sub_data['stripe_subscription_id'],
            'plan_id': plan_id,
            'billing_interval': billing_interval,
            'status': subscription.status,
        }
    )

    logger.info(f"Synced subscription {stripe_sub_data['stripe_subscription_id']} for company {company.name} (status: {subscription.status})")

    # Fail-safe: If we are on localhost or webhooks are delayed, process the latest invoice immediately
    try:
        import stripe
        sub_obj = stripe.Subscription.retrieve(stripe_sub_id)
        latest_invoice_id = getattr(sub_obj, 'latest_invoice', None)
        if latest_invoice_id:
            # Check if we already processed this invoice
            if not Payment.objects.filter(stripe_invoice_id=latest_invoice_id).exists():
                invoice = stripe.Invoice.retrieve(latest_invoice_id)
                if invoice.status == 'paid':
                    logger.info(f"Fail-safe processing of invoice {latest_invoice_id} during checkout sync")
                    invoice_dict = invoice.to_dict() if hasattr(invoice, 'to_dict') else dict(invoice)
                    # Inject subscription ID if missing, which happens in some API versions
                    if not invoice_dict.get('subscription'):
                        invoice_dict['subscription'] = stripe_sub_id
                    
                    webhook_view = StripeWebhookView()
                    webhook_view._handle_invoice_paid(invoice_dict)
    except Exception as e:
        logger.error(f"Error in fail-safe invoice processing: {e}")

# Legacy alias for backward compatibility (e.g. if called from webhook handler)
_sync_subscription_from_session = _sync_subscription_from_stripe_id