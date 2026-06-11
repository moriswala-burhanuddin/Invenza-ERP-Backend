import django
import os
import sys

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')
django.setup()

from django.db import connection

with connection.cursor() as c:
    # Drop old erp_core tables in safe order (CASCADE handles references)
    tables = [
        'erp_core_delivery', 'erp_core_workorder', 'erp_core_salepayment',
        'erp_core_giftcard', 'erp_core_sale', 'erp_core_product',
        'erp_core_customer', 'erp_core_account', 'erp_core_category',
        'erp_core_taxslab', 'erp_core_store',
    ]
    for t in tables:
        c.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
        print(f'Dropped (if existed): {t}')

    # Remove old migration record so Django will apply fresh ones
    c.execute("DELETE FROM django_migrations WHERE app = 'erp_core'")
    print('Cleared erp_core migration history.')

print('Done! Now run: python manage.py makemigrations erp_core && python manage.py migrate')
