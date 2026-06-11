from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Company
from .serializers import SignupSerializer, CompanySerializer, EmailTokenObtainPairSerializer

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer

class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [] # Allow anyone to signup

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, company = serializer.save()
        return Response({
            "user_id": user.id,
            "company_id": company.id,
            "company_name": company.name,
            "message": "User and Company created successfully."
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
            plan_name = company.subscription.plan.name if company.subscription and company.subscription.plan else "Free Tier"
        except:
            plan_name = "Trial"
            
        return Response({
            "login_id": request.user.email,
            "erp_password": company.erp_password,
            "company_name": company.name,
            "subscription_status": company.subscription_status,
            "plan_name": plan_name,
            "trial_days": company.trial_days_left
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
