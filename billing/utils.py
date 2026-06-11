import razorpay
from django.conf import settings
import os

client = razorpay.Client(auth=(os.getenv('RAZORPAY_KEY_ID'), os.getenv('RAZORPAY_KEY_SECRET')))

def create_razorpay_order(amount_in_paise, currency="INR"):
    data = {
        "amount": amount_in_paise,
        "currency": currency,
        "payment_capture": 1 # Auto capture
    }
    order = client.order.create(data=data)
    return order

def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    try:
        client.utility.verify_payment_signature(params_dict)
        return True
    except:
        return False
