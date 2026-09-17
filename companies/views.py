from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings
import requests
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Company
from .serializers import SignupSerializer, CompanySerializer, EmailTokenObtainPairSerializer, CompanySetupSerializer

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer

class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [] # Allow anyone to signup

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        
        user = result['user']
        
        return Response({
            "user_id": user.id,
            "message": "User created successfully. Please check your email to verify your account."
        }, status=status.HTTP_201_CREATED)

class CompanySetupView(generics.CreateAPIView):
    serializer_class = CompanySetupSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Check if user already has a company
        if Company.objects.filter(owner=request.user).exists():
            return Response({"error": "You already have a company setup."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        
        company = result['company']
        
        # Send welcome email now that company is set up
        from .utils import send_welcome_email
        send_welcome_email(request.user, company)
        
        return Response({
            "company_id": company.id,
            "company_name": company.name,
            "message": "Company setup complete. Your trial has started."
        }, status=status.HTTP_201_CREATED)

class CompanyDetailView(generics.RetrieveUpdateAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    lookup_field = 'id'
    permission_classes = [permissions.IsAuthenticated]

class ERPCredentialsView(generics.RetrieveAPIView):
    queryset = Company.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        company = get_object_or_404(Company, owner=request.user)
        try:
            subscription = company.subscription
            plan_name = subscription.plan.name if subscription.plan else "Free Tier"
            status = subscription.status
            sub_status = status.lower() if status else company.subscription_status
            
            # Fetch the latest payment and its invoice
            latest_invoice_url = None
            if subscription.last_payment and hasattr(subscription.last_payment, 'invoice') and subscription.last_payment.invoice.pdf_path:
                latest_invoice_url = request.build_absolute_uri(subscription.last_payment.invoice.pdf_path.url)
            
            expiry_date = subscription.expiry_date.isoformat() if subscription.expiry_date else None
            
        except Exception as e:
            plan_name = "Trial"
            sub_status = company.subscription_status
            latest_invoice_url = None
            expiry_date = None
            
        return Response({
            "login_id": request.user.email,
            "company_id": company.id,
            "company_name": company.name,
            "subscription_status": sub_status,
            "plan_name": plan_name,
            "trial_days": company.trial_days_left,
            "expiry_date": expiry_date,
            "latest_invoice_url": latest_invoice_url
        })

class CheckEmailView(generics.GenericAPIView):
    permission_classes = [] # Allow anyone to check email availability
    
    def get(self, request, *args, **kwargs):
        email = request.query_params.get('email', '').strip().lower()
        if not email:
            return Response({"error": "Email parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        exists = User.objects.filter(email__iexact=email).exists()
        return Response({
            "email": email,
            "available": not exists,
            "message": "Email is available" if not exists else "This email is already registered to another account."
        }, status=status.HTTP_200_OK)

class VerifyEmailView(generics.GenericAPIView):
    permission_classes = []
    
    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        if not token:
            return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        from .utils import verify_token
        from rest_framework_simplejwt.tokens import RefreshToken
        user_id = verify_token(token)
        if not user_id:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)
            
        user = get_object_or_404(User, id=user_id)
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # If user has a company, mark it verified just in case
        company = Company.objects.filter(owner=user).first()
        if company and not company.is_email_verified:
            company.is_email_verified = True
            company.save()
            
        return Response({
            "message": "Email verified successfully.",
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }, status=status.HTTP_200_OK)

class RequestPasswordResetView(generics.GenericAPIView):
    permission_classes = []
    
    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.filter(email__iexact=email).first()
        if user:
            from .utils import send_password_reset_email
            frontend_url = request.headers.get('Origin', 'http://localhost:5173')
            send_password_reset_email(user, frontend_url)
            
        return Response({"message": "If an account with that email exists, we have sent a password reset link."}, status=status.HTTP_200_OK)

class ResetPasswordView(generics.GenericAPIView):
    permission_classes = []
    
    def post(self, request, *args, **kwargs):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('password')
        
        if not uidb64 or not token or not new_password:
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.utils.http import urlsafe_base64_decode
        from django.contrib.auth.tokens import default_token_generator
        
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
            
        if user and default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.save()
            
            from .utils import send_password_changed_email
            send_password_changed_email(user)
            
            return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)

