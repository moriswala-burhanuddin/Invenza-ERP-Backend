import logging
import traceback
from django.db.models import Q
from erp_core.models import *
from .utils import to_decimal, to_date, to_time, parse_payroll_month_year

logger = logging.getLogger('erp_core.sync')

def handle_categories(payload_data, company, synced_ids, errors):
    cat_payload = payload_data
    for row in cat_payload:
        obj_id = row.get('id')
        Category.objects.update_or_create(
            id=obj_id,
            company=company,
            defaults={
                'store_id':    row.get('store_id'),
                'name':        row.get('name'),
                'description': row.get('description'),
                'device_id':   row.get('device_id'),
                'sync_status': 1,
                'is_deleted':  bool(row.get('is_deleted', 0)),
                'deleted_at':  row.get('deleted_at'),
            }
        )
        synced_ids.setdefault('categories', []).append(obj_id)

    

def handle_stores(payload_data, company, synced_ids, errors):
    stores_payload = payload_data
    print(f"[SYNC] Processing {len(stores_payload)} stores...")
    for row in stores_payload:
        obj_id = row.get('id')
        if not obj_id:
            continue
        Store.objects.update_or_create(
            id=obj_id,
            company=company,   # TENANT GUARD: prevent writing to another company
            defaults={
                'name':       row.get('name', ''),
                'branch':     row.get('branch'),
                'address':    row.get('address'),
                'phone':      row.get('phone'),
                'device_id':  row.get('device_id'),
                'sync_status': 1,
                'is_deleted':  bool(row.get('is_deleted', 0)),
                'deleted_at':  row.get('deleted_at'),
            }
        )
        synced_ids.setdefault('stores', []).append(obj_id)

    

def handle_users(payload_data, company, synced_ids, errors):
    users_payload = payload_data
    print(f"[SYNC] Processing {len(users_payload)} users...")
    for row in users_payload:
        obj_id = row.get('id')
        print(f"[SYNC] Pushing User: {row.get('email', obj_id)}")
        if not obj_id:
            continue

        # Security: only update users belonging to this company
        user_defaults = {
            'name':          row.get('name') or row.get('username') or '',
            'email':         row.get('email') or '',
            'username':      row.get('username') or '',
            'role':          row.get('role') or 'staff',
            'first_name':    row.get('first_name') or '',
            'last_name':     row.get('last_name') or '',
            'avatar':        row.get('avatar'),
            'phone':         row.get('phone'),
            'bio':           row.get('bio'),
            'address_line1': row.get('address_line1'),
            'address_line2': row.get('address_line2'),
            'city':          row.get('city'),
            'state':         row.get('state'),
            'country':       row.get('country'),
            'pincode':       row.get('pincode'),
            'is_active':     row.get('is_active', True),
            'is_staff':      row.get('is_staff', False),
            'is_driver':     row.get('is_driver', False),
            'device_id':     row.get('device_id'),
            'sync_status':   1,
            'is_deleted':    bool(row.get('is_deleted', 0)),
            'deleted_at':    row.get('deleted_at'),
        }

        # Only update the password if a new hash is provided
        incoming_password = row.get('password')
        if incoming_password:
            user_defaults['password'] = incoming_password

        try:
            # ── PKEY COLLISION GUARD ──────────────────────────────────────────
            # If the ID exists but belongs to a different company, we cannot update it.
            existing_user = ERPUser.objects.filter(id=obj_id).first()
            if existing_user and existing_user.company != company:
                print(f"[SYNC] Posh Collision: {obj_id} belongs to another company!")
                continue 

            # ── TENANT-BASED UNIQUENESS PRE-CHECK ─────────────────────────────
            conflict_user = ERPUser.objects.filter(
                Q(email__iexact=row.get('email')) | Q(username__iexact=row.get('username')),
                company=company
            ).exclude(id=obj_id).first()
            
            if conflict_user:
                print(f"[SYNC] Duplicate User conflict within company: {row.get('email')} / {row.get('username')}")
                errors.append({
                    "table": "users", "id": obj_id, 
                    "message": f"User with this email or username already exists in your company."
                })
                continue

            # Check if password changed to invalidate old django password
            password_changed = False
            if existing_user and incoming_password and incoming_password != existing_user.password:
                password_changed = True
                user_defaults['previous_password'] = existing_user.password

            erp_user, _ = ERPUser.objects.update_or_create(
                id=obj_id,
                company=company,   # TENANT GUARD
                defaults=user_defaults
            )
            
            incoming_store = row.get('store_id')
            if incoming_store:
                try:
                    store_obj = Store.objects.get(id=incoming_store, company=company)
                    erp_user.stores.add(store_obj)
                except Store.DoesNotExist:
                    pass

            # Skip Django auth bridge for deleted users, but ensure they are deactivated
            if erp_user.is_deleted:
                if erp_user.django_user:
                    erp_user.django_user.is_active = False
                    # Prefix email/username to avoid unique constraints if they sign up again
                    if not erp_user.django_user.email.startswith('__DEL__'):
                        erp_user.django_user.email = f"__DEL__{erp_user.django_user.email}"
                    if not erp_user.django_user.username.startswith('__DEL__'):
                        erp_user.django_user.username = f"__DEL__{erp_user.django_user.username}"
                    erp_user.django_user.save()
                    
                synced_ids.setdefault('users', []).append(obj_id)
                continue
            
            # ── BRIDGE: SYNC TO DJANGO AUTH ───────────────────────────
            if not erp_user.django_user:
                from django.contrib.auth.models import User as DjangoUser
                import uuid
                
                # --- GLOBAL UNIQUENESS ENFORCEMENT ---
                # Prevent using an email that is already registered to another company.
                if DjangoUser.objects.filter(email__iexact=erp_user.email).exists():
                    print(f"[SYNC] Global Email Conflict for {erp_user.email}")
                    errors.append({
                        "table": "users", "id": obj_id, 
                        "message": f"Global Conflict: The email '{erp_user.email}' is already in use by another company account."
                    })
                    # We don't link it to the existing user (to avoid context leakage)
                    # Instead, we leave it un-synced until the user provides a unique email.
                    continue

                # We NO LONGER search by email globally to reuse accounts.
                # Reusing accounts by email breaks multi-tenancy isolation.
                # Every ERPUser gets a dedicated DjangoUser.
                
                raw_username = erp_user.username or erp_user.email.split('@')[0]
                unique_username = f"{raw_username}-{uuid.uuid4().hex[:6]}"
                
                print(f"[SYNC] Creating ISOLATED Shadow Django User: {unique_username} for {erp_user.email}")
                
                django_user = DjangoUser(
                    username=unique_username,
                    email=erp_user.email,
                    first_name=erp_user.first_name or '',
                    last_name=erp_user.last_name or '',
                    is_active=True
                )
                # The actual login will check against ERPUser.password
                django_user.set_password(uuid.uuid4().hex)
                django_user.save()
                
                erp_user.django_user = django_user
                erp_user.save()
            else:
                d_user = erp_user.django_user
                d_user.first_name = erp_user.first_name or ''
                d_user.last_name = erp_user.last_name or ''
                
                # Invalidate old Django password if ERP password was changed
                if password_changed:
                    import uuid
                    d_user.set_password(uuid.uuid4().hex)
                    print(f"[SYNC] Invalidating old Django password for {erp_user.email}")
                    
                    try:
                        from companies.utils import send_password_changed_email
                        send_password_changed_email(d_user)
                        print(f"[SYNC] Sent password changed email to {erp_user.email}")
                    except Exception as email_err:
                        print(f"[SYNC] Failed to send password changed email: {str(email_err)}")
                    
                d_user.save()

            synced_ids.setdefault('users', []).append(obj_id)

        except Exception as e:
            print(f"[SYNC] User Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "users", "id": obj_id, "message": str(e)})

    

def handle_user_permissions(payload_data, company, synced_ids, errors):
    perms_payload = payload_data
    print(f"[SYNC] Processing {len(perms_payload)} user permissions...")
    for row in perms_payload:
        obj_id = row.get('id')
        user_id = row.get('user_id')
        if not obj_id or not user_id: continue
        
        try:
            # Tenant Guard: check user exists in this company
            u = ERPUser.objects.filter(id=user_id, company=company).first()
            if not u: 
                print(f"[SYNC] Perims Error: User {user_id} not in company {company.name}")
                continue

            # We UPSERT by ID to match Electron source of truth, 
            # but also enforce one-per-user implicitly via model constraints
            ERPUserPermission.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'erp_user':     u,
                    'permissions': row.get('permissions', {}),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('user_permissions', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] UserPermissions Push ERROR ({obj_id}): {str(e)}")
            errors.append({"table": "user_permissions", "id": obj_id, "message": str(e)})

    

def handle_user_stores(payload_data, company, synced_ids, errors):
    user_stores_payload = payload_data
    print(f"[SYNC] Processing {len(user_stores_payload)} user-store mappings...")
    for row in user_stores_payload:
        u_id = row.get('user_id')
        s_id = row.get('store_id')
        if not u_id or not s_id:
            continue
        u = ERPUser.objects.filter(id=u_id, company=company).first()
        s = Store.objects.filter(id=s_id, company=company).first()
        if u and s:
            u.stores.add(s)
            synced_ids.setdefault('user_stores', []).append(f"{u_id}_{s_id}")

    

def handle_customers(payload_data, company, synced_ids, errors):
    cust_payload = payload_data
    print(f"[SYNC] Processing {len(cust_payload)} customers...")
    for row in cust_payload:
        obj_id = row.get('id')
        try:
            # TENANT GUARD: only write if the store belongs to this company
            if not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                print(f"[SYNC] Customer {obj_id} skipped: store {row.get('store_id')} not in company")
                continue
            Customer.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'store_id':       row.get('store_id'),
                    'name':           row.get('name') or 'Unknown Customer',
                    'phone':          row.get('phone'),
                    'email':          row.get('email'),
                    'area':           row.get('area'),
                    'credit_balance': row.get('credit_balance', 0),
                    'credit_limit':   row.get('credit_limit', 0),
                    'total_purchases':row.get('total_purchases', 0),
                    'source':         row.get('source', 'POS'),
                    'device_id':      row.get('device_id'),
                    'sync_status':    1,
                    'is_deleted':     bool(row.get('is_deleted', 0)),
                    'deleted_at':     row.get('deleted_at'),
                }
            )
            synced_ids.setdefault('customers', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Customer Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "customers", "id": obj_id, "message": str(e)})

    

def handle_accounts(payload_data, company, synced_ids, errors):
    acc_payload = payload_data
    for row in acc_payload:
        obj_id = row.get('id')
        try:
            # TENANT GUARD: only write if the store belongs to this company
            if not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                print(f"[SYNC] Account {obj_id} skipped: store {row.get('store_id')} not in company")
                continue

            Account.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'store_id':    row.get('store_id'),
                    'name':        row.get('name'),
                    'type':        row.get('type', 'cash'),
                    'balance':     to_decimal(row.get('balance', 0)),
                    'device_id':   row.get('device_id'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('accounts', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Account Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "accounts", "id": obj_id, "message": str(e)})


    

def handle_products(payload_data, company, synced_ids, errors):
    prod_payload = payload_data
    for row in prod_payload:
        obj_id = row.get('id')
        try:
            # 🔒 TENANT GUARD: only write if the store belongs to this company
            if row.get('store_id') and not Store.objects.filter(id=row.get('store_id'), company=company).exists():
                print(f"[SYNC] Product {obj_id} skipped: store {row.get('store_id')} not in company")
                continue
            
            # 🔒 PKEY COLLISION GUARD
            existing_product = Product.objects.filter(id=obj_id).first()
            if existing_product and existing_product.company != company:
                print(f"[SYNC] Product Collision: {obj_id} belongs to another company!")
                continue

            Product.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'store_id':         row.get('store_id'),
                    'name':             row.get('name', 'Unnamed Product'),
                    'sku':              row.get('sku', f"legacy-{obj_id[:8]}"),
                    'category_id':      row.get('category_id') or row.get('categoryId'),
                    'selling_price':    to_decimal(row.get('selling_price')),
                    'purchase_price':   to_decimal(row.get('purchase_price')),
                    'quantity':         to_decimal(row.get('quantity', 0)),
                    'unit':             row.get('unit'),
                    'brand':            row.get('brand'),
                    'barcode':          row.get('barcode'),
                    'min_stock':        int(row.get('min_stock', 0) or 0),
                    'reorder_quantity': int(row.get('reorder_quantity', 0) or 0),
                    'is_deleted':       bool(row.get('is_deleted', 0)),
                    'deleted_at':       row.get('deleted_at'),
                    'is_kit':           bool(row.get('is_kit', 0)),
                    'is_serialized':    bool(row.get('is_serialized', 0)),
                    'tax_slab_id':      row.get('tax_slab_id'),
                    'discount_percentage': to_decimal(row.get('discount_percentage', 0)),
                    'price_inr':        to_decimal(row.get('price_inr')),
                    'price_usd':        to_decimal(row.get('price_usd')),
                    'device_id':        row.get('device_id'),
                    'sync_status':      1,
                }
            )
            synced_ids.setdefault('products', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Product Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "products", "id": obj_id, "message": str(e)})

    

def handle_tax_slabs(payload_data, company, synced_ids, errors):
    tax_payload = payload_data
    for row in tax_payload:
        obj_id = row.get('id')
        try:
            store_id = row.get('store_id')
            if not store_id:
                first_store = Store.objects.filter(company=company).first()
                if first_store:
                    store_id = first_store.id
                    
            TaxSlab.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':   store_id,
                    'name':       row.get('name'),
                    'percentage': to_decimal(row.get('percentage')),
                    'device_id':  row.get('device_id'),
                    'is_deleted': bool(row.get('is_deleted', 0)),
                    'deleted_at': row.get('deleted_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('tax_slabs', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] TaxSlab Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "tax_slabs", "id": obj_id, "message": str(e)})

    

def handle_sales(payload_data, company, synced_ids, errors):
    sales_payload = payload_data
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

            Sale.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'store_id':        row.get('store_id'),
                    'customer_id':     row.get('customer_id'),
                    'account_id':      row.get('account_id'),
                    'invoice_number':  row.get('invoice_number'),
                    'type':            row.get('type', 'retail'),
                    'status':          row.get('status', 'completed'),
                    'items':           row.get('items'),
                    'subtotal':        row.get('subtotal'),
                    'discount_amount': row.get('discount_amount', 0),
                    'tax_amount':      row.get('tax_amount', 0),
                    'total_amount':    row.get('total_amount'),
                    'original_amount': to_decimal(row.get('original_amount')),
                    'original_currency': row.get('original_currency'),
                    'profit':          row.get('profit'),
                    'payment_mode':    row.get('payment_mode'),
                    'source':          row.get('source', 'POS'),
                    'date':            to_date(row.get('date')),
                    'device_id':       row.get('device_id'),
                    'is_deleted':      bool(row.get('is_deleted', 0)),
                    'deleted_at':      row.get('deleted_at'),
                    'sync_status':     1,
                }
            )
            synced_ids.setdefault('sales', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Sale Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "sales", "id": obj_id, "message": str(e)})

    

def handle_transactions(payload_data, company, synced_ids, errors):
    trans_payload = payload_data
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

            Transaction.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'store_id':    row.get('store_id'),
                    'account_id':  row.get('account_id'),
                    'customer_id': row.get('customer_id'),
                    'type':        row.get('type'),
                    'amount':      row.get('amount'),
                    'description': row.get('description'),
                    'date':        to_date(row.get('date')),
                    'device_id':   row.get('device_id'),
                    'is_deleted':  bool(row.get('is_deleted', 0)),
                    'deleted_at':  row.get('deleted_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('transactions', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Transaction Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "transactions", "id": obj_id, "message": str(e)})

    

def handle_payment_terms(payload_data, company, synced_ids, errors):
    pt_payload = payload_data
    for row in pt_payload:
        obj_id = row.get('id')
        try:
            PaymentTerm.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'name': row.get('name'),
                    'days': row.get('days', 0),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('payment_terms', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] PaymentTerm Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "payment_terms", "id": obj_id, "message": str(e)})

    

def handle_receivings(payload_data, company, synced_ids, errors):
    recv_payload = payload_data
    for row in recv_payload:
        obj_id = row.get('id')
        try:
            Receiving.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':         row.get('store_id'),
                    'receiving_number': row.get('receiving_number'),
                    'supplier_id':      row.get('supplier_id'),
                    'total_amount':     to_decimal(row.get('total_amount')),
                    'original_amount':  to_decimal(row.get('original_amount')),
                    'original_currency': row.get('original_currency'),
                    'amount_paid':      to_decimal(row.get('amount_paid')),
                    'status':           row.get('status', 'completed'),
                    'is_deleted':       bool(row.get('is_deleted', 0)),
                    'deleted_at':       row.get('deleted_at'),
                    'sync_status':      1,
                }
            )
            synced_ids.setdefault('receivings', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Receiving Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "receivings", "id": obj_id, "message": str(e)})

    

def handle_receiving_items(payload_data, company, synced_ids, errors):
    ri_payload = payload_data
    for row in ri_payload:
        obj_id = row.get('id')
        try:
            ReceivingItem.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':         row.get('store_id'),
                    'receiving_id':     row.get('receiving_id'),
                    'product_id':       row.get('product_id'),
                    'product_name':     row.get('product_name'),
                    'cost':             to_decimal(row.get('cost')),
                    'quantity':         to_decimal(row.get('quantity')),
                    'total':            to_decimal(row.get('total')),
                    'expiry_date':      to_date(row.get('expiry_date')),
                    'sync_status':      1,
                }
            )
            synced_ids.setdefault('receiving_items', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] ReceivingItem Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "receiving_items", "id": obj_id, "message": str(e)})

    

def handle_employees(payload_data, company, synced_ids, errors):
    emp_payload = payload_data
    for row in emp_payload:
        obj_id = row.get('id')
        try:
            # Try to resolve erp_user linkage
            # Local desktop sends 'user_id', check both user_id and erp_user_id
            erp_user_id = row.get('user_id') or row.get('erp_user_id')
            erp_user_obj = None
            if erp_user_id:
                erp_user_obj = ERPUser.objects.filter(id=erp_user_id, company=company).first()
            
            # Fallback to email linkage
            email = row.get('email')
            if not erp_user_obj and email:
                erp_user_obj = ERPUser.objects.filter(email=email, company=company).first()
                if erp_user_obj:
                    erp_user_id = erp_user_obj.id

            try:
                # Standardizing Employee ID as lowercase for robust matching
                norm_id = obj_id.lower() if obj_id else obj_id

                Employee.objects.update_or_create(
                    id=norm_id, company=company,
                    defaults={
                        'store_id':    row.get('store_id'),
                        'erp_user':    erp_user_obj,
                        'user_id':     erp_user_id,
                        'name':        row.get('name'),
                        'email':       email,
                        'department':  row.get('department'),
                        'designation': row.get('designation'),
                        'salary':      to_decimal(row.get('salary')),
                        'joining_date':to_date(row.get('joining_date')),
                        'documents':    row.get('documents'),
                        'is_deleted':   str(row.get('is_deleted', '0')).lower() in ['1', 'true', 't', 'yes', 'y'],
                        'sync_status': 1,
                    }
                )
                synced_ids.setdefault('employees', []).append(obj_id)
            except Exception as e:
                print(f"[SYNC] Employee Push Error ({obj_id}): {str(e)}")
                errors.append({"table": "employees", "id": obj_id, "message": str(e)})

            # NEW: Alignment - Automatically give the User access to the Employee's store
            if erp_user_obj and row.get('store_id'):
                store_to_link = Store.objects.filter(id=row.get('store_id'), company=company).first()
                if store_to_link:
                    erp_user_obj.stores.add(store_to_link)
                    if not erp_user_obj.store_id: # Also set primary if missing
                        erp_user_obj.store_id = store_to_link.id
                    erp_user_obj.save()

            synced_ids.setdefault('employees', []).append(norm_id)
        except Exception as e:
            print(f"[SYNC] Employee Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "employees", "id": obj_id, "message": str(e)})

    

def handle_attendance(payload_data, company, synced_ids, errors):
    att_payload = payload_data
    for row in att_payload:
        obj_id = row.get('id')
        try:
            # Standardizing Employee ID match as lowercase
            raw_emp_id = row.get('employee_id')
            norm_emp_id = raw_emp_id.lower() if raw_emp_id else None

            Attendance.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':    row.get('store_id'),
                    'employee_id': norm_emp_id,
                    'date':        to_date(row.get('date')),
                    'check_in':    to_time(row.get('check_in')),
                    'check_out':   to_time(row.get('check_out')),
                    'status':      row.get('status', 'present'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('attendance', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Attendance Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "attendance", "id": obj_id, "message": str(e)})

    

def handle_leaves(payload_data, company, synced_ids, errors):
    leave_payload = payload_data
    for row in leave_payload:
        obj_id = row.get('id')
        try:
            Leave.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':    row.get('store_id'),
                    'employee_id': row.get('employee_id'),
                    'type':        row.get('type'),
                    'start_date':  to_date(row.get('start_date')),
                    'end_date':    to_date(row.get('end_date')),
                    'status':      row.get('status', 'pending'),
                    'reason':      row.get('reason'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('leaves', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Leave Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "leaves", "id": obj_id, "message": str(e)})

    

def handle_payroll(payload_data, company, synced_ids, errors):
    pay_payload = payload.get('payroll', payload.get('payrolls', []))
    if pay_payload:
        print(f"[SYNC] Processing {len(pay_payload)} payrolls...")
    for row in pay_payload:
        obj_id = row.get('id')
        try:
            # Normalizing employee_id for case-insensitive matches
            raw_emp_id = row.get('employee_id')
            norm_emp_id = raw_emp_id.lower() if raw_emp_id else None
            
            # Mapping human-readable dates (e.g. "April 2026") to numeric values
            p_month, p_year = parse_payroll_month_year(row)
            
            print(f"[SYNC] DEBUG Payroll Push: ObjID={obj_id}, EmpID={norm_emp_id}, Month={p_month}, Year={p_year}, Company={company.name}")

            Payroll.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':     row.get('store_id'),
                    'employee_id':  norm_emp_id,
                    'month':        p_month,
                    'year':         p_year,
                    'basic_salary': to_decimal(row.get('basic_salary')),
                    'allowances':   to_decimal(row.get('allowances')),
                    'deductions':   to_decimal(row.get('deductions')),
                    'net_salary':   to_decimal(row.get('net_salary')),
                    'status':       row.get('status', 'pending'),
                    'payment_date': to_date(row.get('payment_date')),
                    'paid_at':      row.get('paid_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('payroll', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Payroll Push ERROR ({obj_id}): {str(e)}")
            errors.append({"table": "payroll", "id": obj_id, "message": str(e)})

    

def handle_purchase_orders(payload_data, company, synced_ids, errors):
    po_payload = payload_data
    for row in po_payload:
        obj_id = row.get('id')
        try:
            PurchaseOrder.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':    row.get('store_id'),
                    'po_number':   row.get('po_number'),
                    'supplier_id': row.get('supplier_id'),
                    'total_amount':to_decimal(row.get('total_amount')),
                    'items':       row.get('items'),
                    'date':        to_date(row.get('date')),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('purchase_orders', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] PurchaseOrder Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "purchase_orders", "id": obj_id, "message": str(e)})

    

def handle_stock_transfers(payload_data, company, synced_ids, errors):
    st_payload = payload_data
    for row in st_payload:
        obj_id = row.get('id')
        try:
            StockTransfer.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'from_store_id': row.get('from_store_id'),
                    'to_store_id':   row.get('to_store_id'),
                    'items':         row.get('items'),
                    'date':          to_date(row.get('date')),
                    'sync_status':   1,
                }
            )
            synced_ids.setdefault('stock_transfers', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] StockTransfer Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "stock_transfers", "id": obj_id, "message": str(e)})

    

def handle_quotations(payload_data, company, synced_ids, errors):
    quote_payload = payload_data
    for row in quote_payload:
        obj_id = row.get('id')
        try:
            Quotation.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':         row.get('store_id'),
                    'quotation_number': row.get('quotation_number'),
                    'customer_id':      row.get('customer_id'),
                    'customer_name':    row.get('customer_name'),
                    'customer_phone':   row.get('customer_phone'),
                    'total_amount':     to_decimal(row.get('total_amount')),
                    'items':            row.get('items'),
                    'date':             row.get('date'),
                    'expiry_date':      to_date(row.get('expiry_date')),
                    'status':           row.get('status', 'pending'),
                    'notes':            row.get('notes'),
                    'original_amount':  to_decimal(row.get('original_amount')),
                    'original_currency': row.get('original_currency'),
                    'is_deleted':       bool(row.get('is_deleted', 0)),
                    'deleted_at':       row.get('deleted_at'),
                    'sync_status':      1,
                }
            )
            synced_ids.setdefault('quotations', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Quotation Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "quotations", "id": obj_id, "message": str(e)})

    

def handle_invoices(payload_data, company, synced_ids, errors):
    inv_payload = payload_data
    for row in inv_payload:
        obj_id = row.get('id')
        try:
            Invoice.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':       row.get('store_id'),
                    'invoice_number': row.get('invoice_number'),
                    'customer_id':    row.get('customer_id'),
                    'supplier_id':    row.get('supplier_id'),
                    'type':           row.get('type', 'sales'),
                    'status':         row.get('status', 'draft'),
                    'date':           to_date(row.get('date')),
                    'total_amount':   to_decimal(row.get('total_amount')),
                    'original_amount': to_decimal(row.get('original_amount')),
                    'original_currency': row.get('original_currency'),
                    'amount_paid':    to_decimal(row.get('amount_paid')),
                    'amount_due':     to_decimal(row.get('amount_due')),
                    'is_deleted':     bool(row.get('is_deleted', 0)),
                    'deleted_at':     row.get('deleted_at'),
                    'sync_status':    1,
                }
            )
            synced_ids.setdefault('invoices', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Invoice Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "invoices", "id": obj_id, "message": str(e)})

    

def handle_invoice_items(payload_data, company, synced_ids, errors):
    inv_items_payload = payload_data
    for row in inv_items_payload:
        obj_id = row.get('id')
        try:
            InvoiceItem.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':        row.get('store_id'),
                    'invoice_id':      row.get('invoice_id'),
                    'product_id':      row.get('product_id'),
                    'description':     row.get('description'),
                    'quantity':        to_decimal(row.get('quantity')),
                    'unit_price':      to_decimal(row.get('unit_price')),
                    'total':           to_decimal(row.get('total')),
                    'sync_status':     1,
                }
            )
            synced_ids.setdefault('invoice_items', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] InvoiceItem Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "invoice_items", "id": obj_id, "message": str(e)})

    

def handle_sale_payments(payload_data, company, synced_ids, errors):
    sp_payload = payload_data
    for row in sp_payload:
        obj_id = row.get('id')
        try:
            SalePayment.objects.update_or_create(
                id=obj_id,
                # Note: Models might not have company_id if they are deeply nested, 
                # but we assume they belong implicitly via sale_id. We're safe here if company=company isn't defined or if they have it.
                defaults={
                    'sale_id':      row.get('sale_id'),
                    'account_id':   row.get('account_id'),
                    'payment_mode': row.get('payment_mode'),
                    'amount':       to_decimal(row.get('amount')),
                    'sync_status':  1,
                }
            )
            synced_ids.setdefault('sale_payments', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] SalePayment Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "sale_payments", "id": obj_id, "message": str(e)})

    

def handle_purchases(payload_data, company, synced_ids, errors):
    purchase_payload = payload_data
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

            Purchase.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'supplier_id': row.get('supplier_id'),
                    'account_id': row.get('account_id'),
                    'invoice_number': row.get('invoice_number'),
                    'type': row.get('type'),
                    'items': row.get('items'),
                    'total_amount': to_decimal(row.get('total_amount')),
                    'original_amount': to_decimal(row.get('original_amount')),
                    'original_currency': row.get('original_currency'),
                    'date': row.get('date'),
                    'is_deleted': bool(row.get('is_deleted', 0)),
                    'deleted_at': row.get('deleted_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('purchases', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Purchase Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "purchases", "id": obj_id, "message": str(e)})

    

def handle_cheques(payload_data, company, synced_ids, errors):
    cheque_payload = payload_data
    for row in cheque_payload:
        obj_id = row.get('id')
        try:
            Cheque.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'party_type': row.get('party_type'),
                    'party_id': row.get('party_id'),
                    'party_name': row.get('party_name'),
                    'cheque_number': row.get('cheque_number'),
                    'bank_name': row.get('bank_name'),
                    'amount': row.get('amount'),
                    'issue_date': to_date(row.get('issue_date')),
                    'clearing_date': to_date(row.get('clearing_date')),
                    'status': row.get('status'),
                    'notes': row.get('notes'),
                    'is_deleted': row.get('is_deleted', False),
                    'deleted_at': row.get('deleted_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('cheques', []).append(obj_id)
        except Exception as e:
            print(f"[SYNC] Cheque Push Error ({obj_id}): {str(e)}")
            errors.append({"table": "cheques", "id": obj_id, "message": str(e)})

    

def handle_expense_categories(payload_data, company, synced_ids, errors):
    expense_category_payload = payload_data
    for row in expense_category_payload:
        obj_id = row.get('id')
        try:
            ExpenseCategory.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'name': row.get('name'),
                    'parent_id': row.get('parent_id'),
                    'sync_status': 1,
                    'is_deleted': bool(row.get('is_deleted', 0)),
                    'deleted_at': row.get('deleted_at'),
                }
            )
            synced_ids.setdefault('expense_categories', []).append(obj_id)
        except Exception: pass

    

def handle_loyalty_points(payload_data, company, synced_ids, errors):
    loyalty_point_payload = payload_data
    for row in loyalty_point_payload:
        obj_id = row.get('id')
        try:
            LoyaltyPoint.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'customer_id': row.get('customer_id'),
                    'points': row.get('points'),
                    'reason': row.get('reason'),
                    'sale_id': row.get('sale_id'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('loyalty_points', []).append(obj_id)
        except Exception: pass

    

def handle_commissions(payload_data, company, synced_ids, errors):
    commission_payload = payload_data
    for row in commission_payload:
        obj_id = row.get('id')
        try:
            Commission.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'erp_user_id': row.get('erp_user_id'),
                    'sale_id': row.get('sale_id'),
                    'amount': row.get('amount'),
                    'percentage': row.get('percentage'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('commissions', []).append(obj_id)
        except Exception: pass

    

def handle_work_orders(payload_data, company, synced_ids, errors):
    work_order_payload = payload_data
    for row in work_order_payload:
        obj_id = row.get('id')
        try:
            WorkOrder.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'sale_id': row.get('sale_id'),
                    'status': row.get('status'),
                    'notes': row.get('notes'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('work_orders', []).append(obj_id)
        except Exception: pass

    

def handle_delivery_zones(payload_data, company, synced_ids, errors):
    delivery_zone_payload = payload_data
    for row in delivery_zone_payload:
        obj_id = row.get('id')
        try:
            DeliveryZone.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'name': row.get('name'),
                    'fee': row.get('fee'),
                    'is_active': row.get('is_active'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('delivery_zones', []).append(obj_id)
        except Exception: pass

    

def handle_deliveries(payload_data, company, synced_ids, errors):
    delivery_payload = payload.get('deliveries', payload.get('deliverys', []))
    if delivery_payload:
        print(f"[SYNC] Processing {len(delivery_payload)} deliveries...")
    for row in delivery_payload:
        obj_id = row.get('id')
        try:
            Delivery.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'sale_id': row.get('sale_id'),
                    'employee_id': row.get('employee_id'),
                    'delivery_provider': row.get('delivery_provider'),
                    'tracking_number': row.get('tracking_number'),
                    'delivery_type': row.get('delivery_type'),
                    'address': row.get('address'),
                    'delivery_charge': row.get('delivery_charge'),
                    'is_cod': row.get('is_cod'),
                    'status': row.get('status'),
                    'delivery_date': to_date(row.get('delivery_date')),
                    'notes': row.get('notes'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('deliveries', []).append(obj_id)
        except Exception: pass

    

def handle_shifts(payload_data, company, synced_ids, errors):
    shift_payload = payload_data
    for row in shift_payload:
        obj_id = row.get('id')
        try:
            Shift.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'employee_id': row.get('employee_id'),
                    'start_time': row.get('start_time'),
                    'end_time': row.get('end_time'),
                    'type': row.get('type'),
                    'status': row.get('status'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('shifts', []).append(obj_id)
        except Exception: pass

    

def handle_custom_fields(payload_data, company, synced_ids, errors):
    custom_field_payload = payload_data
    for row in custom_field_payload:
        obj_id = row.get('id')
        try:
            CustomField.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'label': row.get('label'),
                    'type': row.get('type'),
                    'options': row.get('options'),
                    'is_required': row.get('is_required'),
                    'show_on_receipt': row.get('show_on_receipt'),
                    'target_type': row.get('target_type'),
                    'is_deleted': bool(row.get('is_deleted', 0)),
                    'deleted_at': row.get('deleted_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('custom_fields', []).append(obj_id)
        except Exception: pass

    

def handle_product_custom_values(payload_data, company, synced_ids, errors):
    product_custom_value_payload = payload_data
    for row in product_custom_value_payload:
        obj_id = row.get('id')
        try:
            ProductCustomValue.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'product_id': row.get('product_id'),
                    'field_id': row.get('field_id'),
                    'value': row.get('value'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('product_custom_values', []).append(obj_id)
        except Exception: pass

    

def handle_item_kits(payload_data, company, synced_ids, errors):
    item_kit_payload = payload_data
    for row in item_kit_payload:
        obj_id = row.get('id')
        try:
            ItemKit.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'name': row.get('name'),
                    'sku': row.get('sku'),
                    'category': row.get('category'),
                    'selling_price': row.get('selling_price'),
                    'is_active': row.get('is_active'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('item_kits', []).append(obj_id)
        except Exception: pass

    

def handle_kit_items(payload_data, company, synced_ids, errors):
    kit_item_payload = payload_data
    for row in kit_item_payload:
        obj_id = row.get('id')
        try:
            KitItem.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'kit_id': row.get('kit_id'),
                    'product_id': row.get('product_id'),
                    'quantity': row.get('quantity'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('kit_items', []).append(obj_id)
        except Exception: pass

    

def handle_supplier_custom_fields(payload_data, company, synced_ids, errors):
    supplier_custom_field_payload = payload_data
    for row in supplier_custom_field_payload:
        obj_id = row.get('id')
        try:
            SupplierCustomField.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'name': row.get('name'),
                    'field_type': row.get('field_type'),
                    'is_required': row.get('is_required'),
                    'show_on_receipt': row.get('show_on_receipt'),
                    'hide_label': row.get('hide_label'),
                    'options': row.get('options'),
                    'is_deleted': bool(row.get('is_deleted', 0)),
                    'deleted_at': row.get('deleted_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('supplier_custom_fields', []).append(obj_id)
        except Exception: pass

    

def handle_supplier_custom_values(payload_data, company, synced_ids, errors):
    supplier_custom_field_value_payload = payload_data
    for row in supplier_custom_field_value_payload:
        obj_id = row.get('id')
        try:
            SupplierCustomFieldValue.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'supplier_id': row.get('supplier_id'),
                    'field_id': row.get('field_id'),
                    'value': row.get('value'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('supplier_custom_field_values', []).append(obj_id)
        except Exception: pass

    

def handle_supplier_documents(payload_data, company, synced_ids, errors):
    supplier_document_payload = payload_data
    for row in supplier_document_payload:
        obj_id = row.get('id')
        try:
            SupplierDocument.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'supplier_id': row.get('supplier_id'),
                    'name': row.get('name'),
                    'file_path': row.get('file_path'),
                    'file_type': row.get('file_type'),
                    'uploaded_at': row.get('uploaded_at'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('supplier_documents', []).append(obj_id)
        except Exception: pass

    

def handle_supplier_transactions(payload_data, company, synced_ids, errors):
    supplier_transaction_payload = payload_data
    for row in supplier_transaction_payload:
        obj_id = row.get('id')
        try:
            SupplierTransaction.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'supplier_id': row.get('supplier_id'),
                    'type': row.get('type'),
                    'amount': row.get('amount'),
                    'balance_after': row.get('balance_after'),
                    'date': row.get('date'),
                    'reference_id': row.get('reference_id'),
                    'description': row.get('description'),
                    'status': row.get('status'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('supplier_transactions', []).append(obj_id)
        except Exception: pass

    

def handle_candidates(payload_data, company, synced_ids, errors):
    candidate_payload = payload_data
    for row in candidate_payload:
        obj_id = row.get('id')
        try:
            Candidate.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'name': row.get('name'),
                    'email': row.get('email'),
                    'phone': row.get('phone'),
                    'role': row.get('role'),
                    'status': row.get('status'),
                    'resume_text': row.get('resume_text'),
                    'score': row.get('score'),
                    'skills': row.get('skills'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('candidates', []).append(obj_id)
        except Exception: pass

    

def handle_performance_reviews(payload_data, company, synced_ids, errors):
    performance_review_payload = payload_data
    for row in performance_review_payload:
        obj_id = row.get('id')
        try:
            PerformanceReview.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'employee_id': row.get('employee_id'),
                    'review_date': to_date(row.get('review_date')),
                    'reviewer_id': row.get('reviewer_id'),
                    'rating': row.get('rating'),
                    'comments': row.get('comments'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('performance_reviews', []).append(obj_id)
        except Exception: pass

    

def handle_gift_cards(payload_data, company, synced_ids, errors):
    gift_card_payload = payload_data
    for row in gift_card_payload:
        obj_id = row.get('id')
        try:
            GiftCard.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id': row.get('store_id'),
                    'customer_id': row.get('customer_id'),
                    'card_number': row.get('card_number'),
                    'value': row.get('value'),
                    'balance': row.get('balance'),
                    'is_active': row.get('is_active'),
                    'sync_status': 1,
                }
            )
            synced_ids.setdefault('gift_cards', []).append(obj_id)
        except Exception: pass





def handle_suppliers(payload_data, company, synced_ids, errors):
    sup_payload = payload_data
    for row in sup_payload:
        obj_id = row.get('id')
        try:
            Supplier.objects.update_or_create(
                id=obj_id, company=company,
                defaults={
                    'store_id':       row.get('store_id'),
                    'supplier_code':  row.get('supplier_code') or obj_id[:8],
                    'company_name':   row.get('company_name') or row.get('name') or '',
                    'first_name':     row.get('first_name') or '',
                    'last_name':      row.get('last_name') or '',
                    'email':          row.get('email'),
                    'phone':          row.get('phone'),
                    'address_line1':  row.get('address_line1'),
                    'city':           row.get('city'),
                    'state':          row.get('state'),
                    'country':        row.get('country'),
                    'currency':       row.get('currency', 'USD'),
                    'status':         row.get('status', 'active'),
                    'is_deleted':      bool(row.get('is_deleted', 0)),
                    'deleted_at':      row.get('deleted_at'),
                    'sync_status':    1,
                }
            )
            synced_ids.setdefault('suppliers', []).append(obj_id)
        except Exception as e:
            logger.error(f"[SYNC] suppliers Push Error on ID {obj_id}: {str(e)}")
            logger.error(traceback.format_exc())
            errors.append({"table": "suppliers", "id": obj_id, "message": str(e)})

def handle_stock_logs(payload_data, company, synced_ids, errors):
    log_payload = payload_data
    for row in log_payload:
        obj_id = row.get('id')
        try:
            StockLog.objects.update_or_create(
                id=obj_id,
                company=company,
                defaults={
                    'store_id':        row.get('store_id'),
                    'product_id':      row.get('product_id'),
                    'quantity_change': row.get('quantity_change'),
                    'reason':          row.get('reason'),
                    'reference_id':    row.get('reference_id'),
                    'device_id':       row.get('device_id'),
                    'sync_status':     1,
                }
            )   
            synced_ids.setdefault('stock_logs', []).append(obj_id)
        except Exception as e:
            logger.error(f"[SYNC] stock_logs Push Error on ID {obj_id}: {str(e)}")
            logger.error(traceback.format_exc())
            errors.append({"table": "stock_logs", "id": obj_id, "message": str(e)})
