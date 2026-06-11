import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()

from django.contrib.auth import get_user_model
from companies.models import Company
from erp_core.models import ERPUser
User = get_user_model()
u = User.objects.filter(email='codecraft.burhanuddin@gmail.com').first()
if u:
    print(f'\n--- DATABASE CHECK ---')
    print(f'User: {u.first_name} {u.last_name} ({u.email})')
    comp = u.owned_companies.first()
    print(f'Company: {comp}')
    if comp:
        erp_users = ERPUser.objects.filter(company=comp)
        print('ERP Users:')
        for eu in erp_users:
            print(f'  - {eu.name} ({eu.email}) - Role: {eu.role}')
    else:
        print('No company found for this user.')
    print(f'----------------------\n')
else:
    print('\nUser not found.\n')
