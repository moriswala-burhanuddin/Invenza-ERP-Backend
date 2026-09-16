import re

views_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\views.py'
handlers_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py'
dispatcher_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\dispatcher.py'

with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

missing_blocks = re.findall(r'# [─]+ PUSH SUPPLIERS ─────\n(.*?)# ──', content, re.DOTALL)
if missing_blocks:
    suppliers_code = missing_blocks[0]
    # process it
    suppliers_code = '\n'.join(['    ' + line[12:] if line.startswith('            ') else line for line in suppliers_code.split('\n')])
    suppliers_code = re.sub(
        r'except Exception as e:\s+print\([^)]+\)\s+errors\.append\([^)]+\)',
        f'except Exception as e:\n        logger.error(f"[SYNC] suppliers Push Error on ID {{obj_id}}: {{str(e)}}")\n        logger.error(traceback.format_exc())\n        errors.append({{"table": "suppliers", "id": obj_id, "message": str(e)}})',
        suppliers_code
    )
    suppliers_func = f'def handle_suppliers(payload_data, company, synced_ids, errors):\n    sup_payload = payload_data\n{suppliers_code}\n\n'
    with open(handlers_path, 'a', encoding='utf-8') as f:
        f.write(suppliers_func)
    
missing_blocks2 = re.findall(r'# [─]+ PUSH STOCK LOGS ─────\n(.*?)# ──', content, re.DOTALL)
if missing_blocks2:
    sl_code = missing_blocks2[0]
    sl_code = '\n'.join(['    ' + line[12:] if line.startswith('            ') else line for line in sl_code.split('\n')])
    sl_code = re.sub(
        r'except Exception as e:\s+print\([^)]+\)\s+errors\.append\([^)]+\)',
        f'except Exception as e:\n        logger.error(f"[SYNC] stock_logs Push Error on ID {{obj_id}}: {{str(e)}}")\n        logger.error(traceback.format_exc())\n        errors.append({{"table": "stock_logs", "id": obj_id, "message": str(e)}})',
        sl_code
    )
    sl_func = f'def handle_stock_logs(payload_data, company, synced_ids, errors):\n    sl_payload = payload_data\n{sl_code}\n\n'
    with open(handlers_path, 'a', encoding='utf-8') as f:
        f.write(sl_func)

# Also update dispatcher
with open(dispatcher_path, 'r', encoding='utf-8') as f:
    dcontent = f.read()

dcontent = dcontent.replace('PUSH_HANDLERS = {', "PUSH_HANDLERS = {\n    'suppliers': handle_suppliers,\n    'stock_logs': handle_stock_logs,")

with open(dispatcher_path, 'w', encoding='utf-8') as f:
    f.write(dcontent)

print("Suppliers and Stock logs added!")
