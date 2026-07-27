import re

file_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\views.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 3. PUSH QUOTATIONS
quotation_replacement = '''            quotation_payload = payload.get('quotations', [])
            for row in quotation_payload:
                obj_id = row.get('id')
                try:
                    # ?? TENANT GUARD
                    if row.get('store_id') and not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                        continue
                    if row.get('customer_id') and not Customer.objects.filter(id=row.get('customer_id'), company=company).exists():
                        continue

                    # ?? PKEY GUARD
                    existing_q = Quotation.objects.filter(id=obj_id).first()
                    if existing_q and existing_q.company_id != company.id:
                        continue

                    Quotation.objects.update_or_create('''

content = re.sub(
    r"            quotation_payload = payload\.get\('quotations', \[\]\)\n            for row in quotation_payload:\n                obj_id = row\.get\('id'\)\n                try:\n                    Quotation\.objects\.update_or_create\(",
    quotation_replacement,
    content
)

# 4. PUSH PURCHASES
purchase_replacement = '''            purchase_payload = payload.get('purchases', [])
            for row in purchase_payload:
                obj_id = row.get('id')
                try:
                    # ?? TENANT GUARD
                    if row.get('store_id') and not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                        continue
                    if row.get('supplier_id') and not Supplier.objects.filter(id=row.get('supplier_id'), company=company).exists():
                        continue
                    
                    # ?? PKEY GUARD
                    existing_p = Purchase.objects.filter(id=obj_id).first()
                    if existing_p and existing_p.company_id != company.id:
                        continue

                    Purchase.objects.update_or_create('''

content = re.sub(
    r"            purchase_payload = payload\.get\('purchases', \[\]\)\n            for row in purchase_payload:\n                obj_id = row\.get\('id'\)\n                try:\n                    Purchase\.objects\.update_or_create\(",
    purchase_replacement,
    content
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Patch applied successfully')
