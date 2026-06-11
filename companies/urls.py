from django.urls import path
from .views import SignupView, MyTokenObtainPairView, CompanyDetailView, ERPCredentialsView, CheckEmailView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('check-email/', CheckEmailView.as_view(), name='check_email'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair_compat'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('companies/<int:id>/', CompanyDetailView.as_view(), name='company_detail'),
    path('erp-credentials/', ERPCredentialsView.as_view(), name='erp_credentials'),
]
