import re

file_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\views.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. PUSH SALES
sales_replacement = '''            sales_payload = payload.get('sales', [])
            for row in sales_payload:
                obj_id = row.get('id')
                try:
                    # ?? TENANT GUARD
                    if row.get('store_id') and not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                        print(f"[SYNC] Sale {obj_id} skipped: store not in company")
                        continue
                    if row.get('customer_id') and not Customer.objects.filter(id=row.get('customer_id'), company=company).exists():
                        print(f"[SYNC] Sale {obj_id} skipped: customer not in company")
                        continue
                    if row.get('account_id') and not Account.objects.filter(id=row.get('account_id'), company=company).exists():
                        print(f"[SYNC] Sale {obj_id} skipped: account not in company")
                        continue

                    # ?? PKEY GUARD
                    existing_sale = Sale.objects.filter(id=obj_id).first()
                    if existing_sale and existing_sale.company_id != company.id:
                        print(f"[SYNC] Sale Collision: {obj_id} belongs to another company!")
                        continue

                    Sale.objects.update_or_create('''

content = re.sub(
    r"            sales_payload = payload\.get\('sales', \[\]\)\n            for row in sales_payload:\n                obj_id = row\.get\('id'\)\n                try:\n                    Sale\.objects\.update_or_create\(",
    sales_replacement,
    content
)

# 2. PUSH TRANSACTIONS
trans_replacement = '''            trans_payload = payload.get('transactions', [])
            for row in trans_payload:
                obj_id = row.get('id')
                try:
                    # ?? TENANT GUARD
                    if row.get('store_id') and not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                        continue
                    if row.get('customer_id') and not Customer.objects.filter(id=row.get('customer_id'), company=company).exists():
                        continue
                    if row.get('account_id') and not Account.objects.filter(id=row.get('account_id'), company=company).exists():
                        continue

                    # ?? PKEY GUARD
                    existing_trans = Transaction.objects.filter(id=obj_id).first()
                    if existing_trans and existing_trans.company_id != company.id:
                        continue

                    Transaction.objects.update_or_create('''

content = re.sub(
    r"            trans_payload = payload\.get\('transactions', \[\]\)\n            for row in trans_payload:\n                obj_id = row\.get\('id'\)\n                try:\n                    Transaction\.objects\.update_or_create\(",
    trans_replacement,
    content
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Patch applied successfully')
