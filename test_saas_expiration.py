import os
import django
import sys
import datetime

sys.path.append(r"d:\paid-erp\invenza-erp\invenza-website\backend")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()

from django.utils import timezone
from companies.models import Company

try:
    company = Company.objects.get(name='Webz')
    
    # 1. Test 1-day reminder
    print("Setting company to 1-day left on trial...")
    company.created_at = timezone.now() - datetime.timedelta(days=6)
    company.subscription_status = 'trial'
    company.trial_reminder_sent = False
    company.save()
    print("Done. Now run: python manage.py check_subscriptions")
    
except Exception as e:
    print(f"Error: {e}")
