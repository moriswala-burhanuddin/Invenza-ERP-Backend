from django.urls import path
from .views import CreateOrderView, VerifyPaymentView, ListPlansView

urlpatterns = [
    path('plans/', ListPlansView.as_view(), name='list_plans'),
    path('order/create/', CreateOrderView.as_view(), name='create_order'),
    path('payment/verify/', VerifyPaymentView.as_view(), name='verify_payment'),
]
