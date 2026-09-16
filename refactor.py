import re
import os

views_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\views.py'
handlers_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py'
dispatcher_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\dispatcher.py'

with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We will use regex to find all `# ── PUSH ...` blocks
# The block starts with `# ── PUSH <NAME> ─────`
# and ends when the next `# ── PUSH ` starts, or at the end of the try/except block.

blocks = re.split(r'# [─]+ PUSH (.*?)[ ─]+\n', content)
# blocks[0] is everything before the first push
# blocks[1] is the first name
# blocks[2] is the code
# ...

handlers_code = '''import logging
import traceback
from django.db.models import Q
from erp_core.models import *
from .utils import to_decimal, to_date, to_time, parse_payroll_month_year

logger = logging.getLogger('erp_core.sync')

'''

dispatcher_code = '''from .handlers import *

PUSH_HANDLERS = {
'''

table_map = {
    'CATEGORIES': 'categories',
    'STORES': 'stores',
    'ERP USERS': 'users',
    'USER PERMISSIONS': 'user_permissions',
    'USER STORES (M2M)': 'user_stores',
    'CUSTOMERS': 'customers',
    'ACCOUNTS': 'accounts',
    'PRODUCTS': 'products',
    'TAX SLABS': 'tax_slabs',
    'SALES': 'sales',
    'TRANSACTIONS': 'transactions',
    'PAYMENT TERMS': 'payment_terms',
    'RECEIVINGS': 'receivings',
    'RECEIVING ITEMS': 'receiving_items',
    'EMPLOYEES': 'employees',
    'ATTENDANCE': 'attendance',
    'LEAVES': 'leaves',
    'PAYROLL': 'payroll',
    'PURCHASE ORDERS': 'purchase_orders',
    'STOCK TRANSFERS': 'stock_transfers',
    'QUOTATIONS': 'quotations',
    'INVOICES': 'invoices',
    'INVOICE ITEMS': 'invoice_items',
    'SALE PAYMENTS': 'sale_payments',
    'PURCHASE': 'purchases',
    'CHEQUE': 'cheques',
    'EXPENSECATEGORY': 'expense_categories',
    'LOYALTYPOINT': 'loyalty_points',
    'COMMISSION': 'commissions',
    'WORKORDER': 'work_orders',
    'DELIVERYZONE': 'delivery_zones',
    'DELIVERY': 'deliveries',
    'SHIFT': 'shifts',
    'CUSTOMFIELD': 'custom_fields',
    'PRODUCTCUSTOMVALUE': 'product_custom_values',
    'ITEMKIT': 'item_kits',
    'KITITEM': 'kit_items',
    'SUPPLIERCUSTOMFIELD': 'supplier_custom_fields',
    'SUPPLIERCUSTOMFIELDVALUE': 'supplier_custom_values',
    'SUPPLIERDOCUMENT': 'supplier_documents',
    'SUPPLIERTRANSACTION': 'supplier_transactions',
    'CANDIDATE': 'candidates',
    'PERFORMANCEREVIEW': 'performance_reviews',
    'GIFTCARD': 'gift_cards'
}

for i in range(1, len(blocks), 2):
    header = blocks[i].strip()
    code = blocks[i+1]
    
    if header == 'NEW BUSINESS MODELS PUSH':
        continue
    
    table_key = table_map.get(header)
    if not table_key:
        print("Unknown header:", header)
        continue
    
    # Strip off trailing stuff from the last block
    if header == 'GIFTCARD':
        code = code.split('except Exception as e:')[0] # remove outer except block
    
    func_name = f'handle_{table_key}'
    
    # Unindent everything by 12 spaces (since it was inside a class method loop)
    lines = code.split('\n')
    fixed_lines = []
    for line in lines:
        if line.startswith('            '):
            fixed_lines.append('    ' + line[12:])
        elif line.startswith('        '):
            fixed_lines.append(line[8:])
        else:
            fixed_lines.append(line)
            
    code_str = '\n'.join(fixed_lines)
    
    # Replace the swallow exception block with logging
    code_str = re.sub(
        r'except Exception as e:\s+print\([^)]+\)\s+errors\.append\([^)]+\)',
        f'except Exception as e:\n        logger.error(f"[SYNC] {table_key} Push Error on ID {{obj_id}}: {{str(e)}}")\n        logger.error(traceback.format_exc())\n        errors.append({{"table": "{table_key}", "id": obj_id, "message": str(e)}})',
        code_str
    )
    
    handlers_code += f'def {func_name}(payload_data, company, synced_ids, errors):\n'
    
    payload_var = re.search(r'([a-zA-Z0-9_]+) = payload\.get', code_str)
    if payload_var:
        pvar = payload_var.group(1)
        code_str = re.sub(r'[a-zA-Z0-9_]+ = payload\.get\([^)]+\)\n', f'    {pvar} = payload_data\n', code_str, count=1)
    
    handlers_code += code_str + '\n\n'
    dispatcher_code += f"    '{table_key}': {func_name},\n"

dispatcher_code += '''}

class SyncDispatcher:
    @staticmethod
    def dispatch_push(payload, company):
        synced_ids = {}
        errors = []
        
        for table_name, row_data in payload.items():
            handler = PUSH_HANDLERS.get(table_name)
            if handler:
                try:
                    handler(row_data, company, synced_ids, errors)
                except Exception as e:
                    import logging
                    import traceback
                    logger = logging.getLogger('erp_core.sync')
                    logger.error(f"[SYNC] Critical error in {table_name} handler: {e}")
                    logger.error(traceback.format_exc())
                    errors.append({"table": table_name, "id": "ALL", "message": f"Handler crashed: {str(e)}"})
            else:
                print(f"No handler found for {table_name}")
                
        return {
            "status": "success",
            "synced_ids": synced_ids,
            "errors": errors
        }
'''

with open(handlers_path, 'w', encoding='utf-8') as f:
    f.write(handlers_code)
    
with open(dispatcher_path, 'w', encoding='utf-8') as f:
    f.write(dispatcher_code)
    
print("Handlers and dispatcher generated successfully")
