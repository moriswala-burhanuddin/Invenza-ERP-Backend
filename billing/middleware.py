from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.utils import timezone
from .models import Subscription

class SubscriptionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Allow open endpoints (e.g., login, webhooks, sign up, Stripe)
        open_paths = [
            '/api/companies/login/',
            '/api/companies/signup/',
            '/api/billing/webhook/',
            '/api/billing/stripe-webhook/',
            '/api/billing/create-checkout-session/',
            '/api/billing/checkout-success/',
            '/api/billing/plans/',
            '/api/billing/customer-portal/',
            '/admin/',
        ]
        
        for path in open_paths:
            if request.path.startswith(path):
                return None
                
        # Check authentication
        if not request.user.is_authenticated:
            return None # Let DRF handle auth if it's an API route
            
        company = request.user.owned_companies.first()
        if not company:
            return None
            
        try:
            subscription = company.subscription
        except Subscription.DoesNotExist:
            return JsonResponse({'error': 'Subscription not found'}, status=402)
            
        if subscription.status in ['EXPIRED', 'CANCELLED', 'SUSPENDED']:
            return JsonResponse({
                'error': 'Payment Required',
                'detail': f'Your subscription is {subscription.status.lower()}. Please renew your plan to continue using the ERP.'
            }, status=402)
            
        return None
