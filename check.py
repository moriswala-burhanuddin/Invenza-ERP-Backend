handlers_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py'
with open(handlers_path, 'r', encoding='utf-8') as f:
    if 'def handle_suppliers' in f.read():
        print("handle_suppliers is in handlers.py")
    else:
        print("handle_suppliers IS MISSING")
