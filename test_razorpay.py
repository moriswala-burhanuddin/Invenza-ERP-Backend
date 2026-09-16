import os, sys, django, razorpay
sys.path.append('d:/paid-erp/invenza-erp/invenza-website/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()
from django.conf import settings

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
try:
    razorpay_order = client.order.create({
        'amount': 2900,
        'currency': 'INR',
        'receipt': "receipt_test",
        'payment_capture': '1'
    })
    print("SUCCESS", razorpay_order)
except Exception as e:
    print("ERROR", str(e))
