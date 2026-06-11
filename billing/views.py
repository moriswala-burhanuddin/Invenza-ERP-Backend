from rest_framework import status, views, permissions
from rest_framework.response import Response
import os
from .models import Plan, Feature, Subscription
from .serializers import PlanSerializer, FeatureSerializer
from .utils import create_razorpay_order, verify_payment_signature
from .pdf_generator import generate_subscription_receipt
from companies.models import Company
from django.shortcuts import get_object_or_404
from django.core.mail import EmailMessage
import uuid

class CreateOrderView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        company_id = request.data.get('company_id')
        plan_id = request.data.get('plan_id')
        feature_ids = request.data.get('feature_ids', [])

        company = get_object_or_404(Company, id=company_id)
        plan = get_object_or_404(Plan, id=plan_id)
        features = Feature.objects.filter(id__in=feature_ids)

        total_amount = plan.monthly_price
        for feature in features:
            total_amount += feature.price

        # Convert to paise
        amount_in_paise = int(total_amount * 100)
        
        try:
            order = create_razorpay_order(amount_in_paise)
            
            # Create or update subscription record with order_id
            subscription, created = Subscription.objects.get_or_create(company=company)
            subscription.plan = plan
            subscription.order_id = order['id']
            subscription.save()
            subscription.features.set(features)

            return Response({
                "order_id": order['id'],
                "amount": total_amount,
                "currency": "INR",
                "key_id": os.getenv('RAZORPAY_KEY_ID')
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class VerifyPaymentView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')

        if verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            subscription = get_object_or_404(Subscription, order_id=razorpay_order_id)
            subscription.payment_id = razorpay_payment_id
            subscription.is_active = True
            subscription.save()

            # Enable features on Company model
            company = subscription.company
            company.subscription_status = 'active'
            
            # Check if AI feature was purchased
            if subscription.features.filter(internal_id='ai_assistant').exists():
                company.is_ai_enabled = True
            
            company.save()

            # Generate receipt info
            subscription.receipt_number = f"INV-{uuid.uuid4().hex[:8].upper()}"
            subscription.amount_paid = subscription.plan.monthly_price + sum(f.price for f in subscription.features.all())
            subscription.save()

            # Generate PDF and Send Email
            try:
                pdf_path = generate_subscription_receipt(subscription)
                from erp_core.services.email_service import EnterpriseEmailService
                
                subject = 'Your Invenza ERP Subscription is Active!'
                message = (
                    f'Hello {subscription.company.name},\n\n'
                    f'Your subscription to the {subscription.plan.name} plan is now active.\n\n'
                    f'Your ERP Credentials:\n'
                    f'- Login Identifier: {subscription.company.id}\n'
                    f'- Temporary ERP Password: {subscription.company.erp_password}\n\n'
                    f'Please keep these safe.\n'
                    f'Thank you,\n'
                    f'The Invenza Team'
                )
                
                # Use company email if available, else user email
                to_email = subscription.company.email or request.user.email
                
                from django.conf import settings
                email = EmailMessage(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [to_email],
                )
                email.attach_file(pdf_path)
                email.send()
                
                print(f"[Email SENT] Subject: {subject}, To: {to_email}")
            except Exception as e:
                print(f"[Email/PDF FAILED] {e}")

            return Response({
                "message": "Payment verified successfully.",
                "erp_credentials": {
                    "login_id": subscription.company.id,
                    "password": subscription.company.erp_password
                },
                "status": "active"
            })
        else:
            return Response({"error": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

class ListPlansView(views.APIView):
    permission_classes = [] # Publicly visible for pricing page
    def get(self, request):
        plans = Plan.objects.filter(is_active=True)
        features = Feature.objects.filter(is_active=True)
        return Response({
            "plans": PlanSerializer(plans, many=True).data,
            "features": FeatureSerializer(features, many=True).data
        })
