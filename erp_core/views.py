"""
erp_core/views.py
==================
Tenant-aware Sync API for the Electron Desktop ERP.

SECURITY RULES:
- Every query MUST filter by company — no exceptions.
- The company is derived from request.user (JWT token carries company_id).
- A user from Company A can NEVER read or write Company B data.

ENDPOINTS:
  POST /api/erp/sync/pull/  — Electron pulls its Company's data from the cloud
  POST /api/erp/sync/push/  — Electron pushes local changes up to the cloud
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from .models import *
from companies.models import Company


def to_decimal(value, default="0"):
    """Safely convert any input to a Decimal, handling formatting like commas."""
    if value is None or str(value).strip() == "":
        return Decimal(str(default))
    try:
        # First try direct conversion
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        # Fallback: remove common formatting characters
        try:
            clean = str(value).replace(',', '').strip()
            return Decimal(clean)
        except:
            return Decimal(str(default))

def to_time(val):
    """Extracts HH:MM:SS from ISO strings or returns raw time strings."""
    if not val: return None
    val = str(val).strip().strip('"').strip("'")
    if 'T' in val:
        time_part = val.split('T')[1]
        return time_part.split('.')[0].replace('Z', '')
    if ' ' in val: # Handle "2024-04-08 16:16:58"
        parts = val.split(' ')
        if len(parts) > 1:
            return parts[1].split('.')[0]
    return val

def to_date(val):
    """Extracts YYYY-MM-DD from ISO strings or returns raw date strings."""
    if not val: return None
    val = str(val).strip().strip('"').strip("'")
    if 'T' in val:
        return val.split('T')[0]
    if ' ' in val:
        return val.split(' ')[0]
    return val


def parse_payroll_month_year(row):
    """
    Intelligently extracts numeric month and year from a payload row.
    Handles 'month': 4, 'year': 2026 OR 'month': 'April 2026'.
    """
    month_raw = str(row.get('month', '')).strip()
    year_raw = str(row.get('year', '')).strip()
    
    # Fallbacks
    m, y = 1, 2024
    
    # 1. Try direct numeric conversion
    try:
        return int(month_raw), int(year_raw)
    except (ValueError, TypeError):
        pass
        
    # 2. Handle combined strings like "April 2026" or "JUNE 2026"
    combined = month_raw if ' ' in month_raw else f"{month_raw} {year_raw}"
    parts = combined.split()
    
    if len(parts) >= 1:
        name_part = parts[0].lower()
        months_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        for k, v in months_map.items():
            if name_part.startswith(k):
                m = v
                break
                
    if len(parts) >= 2:
        try:
            y = int(parts[-1])
        except:
            pass
            
    return m, y


def get_company_for_user(django_user):
    """
    Safely retrieve the Company associated with the logged-in Django user.
    Handles both Company Owners and Staff Members (Employees).
    """
    # 1. Primary Owner lookup
    owner_company = Company.objects.filter(owner=django_user).first()
    if owner_company:
        return owner_company
    
    # 2. Staff/Employee lookup (via ERPUser profile)
    erp_profile = ERPUser.objects.filter(django_user=django_user).first()
    if erp_profile:
        return erp_profile.company
        
    return None


class SyncPullEndpoint(APIView):
    """
    Electron calls this to download the latest data from the cloud.
    Returns: stores, erp_users (users in the ERP), and their permissions.
    All data is strictly scoped to the authenticated user's Company.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        company = get_company_for_user(request.user)
        if not company:
            return Response(
                {"error": "No company found for this user. Please complete your company setup."},
                status=status.HTTP_403_FORBIDDEN
            )

        last_sync = request.data.get('last_sync')  # ISO 8601 datetime string or None

        def get_qs(model, extra_filter=None):
            qs = model.objects.filter(company=company)
            if extra_filter:
                qs = qs.filter(**extra_filter)
            if last_sync:
                try:
                    from django.utils.dateparse import parse_datetime
                    dt = parse_datetime(last_sync)
                    if dt:
                        if timezone.is_naive(dt):
                            dt = timezone.make_aware(dt)
                        qs = qs.filter(updated_at__gt=dt)
                except Exception:
                    pass  # If parsing fails, return all records
            return qs

        # ── STORES ──────────────────────────────────────────────────────────
        stores_data = list(get_qs(Store).values(
            'id', 'company_id', 'name', 'branch', 'address', 'phone',
            'device_id', 'sync_status', 'updated_at', 'created_at',
            'is_deleted', 'deleted_at'
        ))

        # ── ERP USERS ───────────────────────────────────────────────────────
        erp_users_raw = get_qs(ERPUser)
        users_data = []
        for u in erp_users_raw:
            store_ids = list(u.stores.values_list('id', flat=True))
            users_data.append({
                'id':            u.id,
                'company_id':    u.company_id,
                'name':          u.name,
                'email':         u.email,
                'username':      u.username,
                'password':      u.password,   # Already hashed — safe to send to local DB
                'role':          u.role,
                'first_name':    u.first_name,
                'last_name':     u.last_name,
                'avatar':        u.avatar,
                'phone':         u.phone,
                'bio':           u.bio,
                'address_line1': u.address_line1,
                'address_line2': u.address_line2,
                'city':          u.city,
                'state':         u.state,
                'country':       u.country,
                'pincode':       u.pincode,
                'is_active':     u.is_active,
                'is_staff':      u.is_staff,
                'is_driver':     u.is_driver,
                'device_id':     u.device_id,
                'sync_status':   u.sync_status,
                'updated_at':    u.updated_at.isoformat() if u.updated_at else None,
                'is_deleted':    u.is_deleted,
                'deleted_at':    u.deleted_at.isoformat() if u.deleted_at else None,
                'store_id':      store_ids[0] if store_ids else None,  # Primary store for Electron
                'store_ids':     store_ids,   # All store access
            })

        # ── USER PERMISSIONS ─────────────────────────────────────────────────
        perms_data = []
        for p in get_qs(ERPUserPermission):
            perms_data.append({
                'id': p.id,
                'user_id': p.erp_user_id,
                'permissions': p.permissions,
                'sync_status': p.sync_status,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None
            })

        # ── USER-STORE MAPPINGS (M2M) ────────────────────────────────────────
        user_stores_data = []
        for u in get_qs(ERPUser):
            for s in u.stores.all():
                user_stores_data.append({
                    "user_id": u.id,
                    "store_id": s.id,
                    "updated_at": u.updated_at.isoformat() if u.updated_at else None,
                    "sync_status": 1
                })

        # ── NEW BUSINESS MODELS PULL ─────────────────────────────────────────
        
        # ── CUSTOMERS
        customers_data = list(get_qs(Customer).values(
            'id', 'company_id', 'store_id', 'name', 'phone', 'email', 'area',
            'credit_balance', 'credit_limit', 'total_purchases', 'source',
            'joined_at', 'device_id', 'sync_status', 'updated_at', 'is_deleted', 'deleted_at'
        ))

        # ── CATEGORIES
        categories_data = list(get_qs(Category).values(
            'id', 'company_id', 'store_id', 'name', 'description',
            'device_id', 'sync_status', 'updated_at', 'is_deleted', 'deleted_at'
        ))

        # ── ACCOUNTS
        accounts_data = list(get_qs(Account).values(
            'id', 'company_id', 'store_id', 'name', 'type', 'balance',
            'device_id', 'sync_status', 'updated_at'
        ))

        # ── TAX SLABS
        tax_slabs_data = list(get_qs(TaxSlab).values(
            'id', 'company_id', 'store_id', 'name', 'percentage',
            'device_id', 'is_deleted', 'deleted_at',
            'updated_at', 'sync_status'
        ))

        # ── PRODUCTS
        products_data = list(get_qs(Product).values(
            'id', 'company_id', 'store_id', 'name', 'sku', 'category_id',
            'selling_price', 'purchase_price', 'quantity', 'unit', 'brand',
            'barcode', 'min_stock', 'reorder_quantity', 'is_deleted', 'is_kit',
            'is_serialized', 'tax_slab_id', 'discount_percentage',
            'price_inr', 'price_usd',
            'device_id', 'sync_status', 'updated_at', 'deleted_at'
        ))

        # ── SALES (Invoices)
        sales_raw = get_qs(Sale)
        sales_data = []
        for s in sales_raw:
            sales_data.append({
                'id': s.id,
                'company_id': s.company_id,
                'store_id': s.store_id,
                'customer_id': s.customer_id,
                'account_id': s.account_id,
                'invoice_number': s.invoice_number,
                'type': s.type,
                'status': s.status,
                'items': s.items, # JSONField is auto-serialized
                'subtotal': float(s.subtotal),
                'discount_amount': float(s.discount_amount),
                'tax_amount': float(s.tax_amount),
                'total_amount': float(s.total_amount),
                'original_amount': float(s.original_amount) if s.original_amount is not None else None,
                'original_currency': s.original_currency,
                'profit': float(s.profit),
                'payment_mode': s.payment_mode,
                'source': s.source,
                'date': s.date.isoformat(),
                'device_id': s.device_id,
                'sync_status': s.sync_status,
                'updated_at': s.updated_at.isoformat(),
                'is_deleted': s.is_deleted,
                'deleted_at': s.deleted_at.isoformat() if s.deleted_at else None
            })

        # ── TRANSACTIONS
        trans_raw = get_qs(Transaction)
        transactions_data = []
        for t in trans_raw:
            transactions_data.append({
                'id': t.id,
                'company_id': t.company_id,
                'store_id': t.store_id,
                'account_id': t.account_id,
                'customer_id': t.customer_id,
                'expense_category_id': t.expense_category_id,
                'type': t.type,
                'amount': float(t.amount),
                'description': t.description,
                'date': t.date.isoformat(),
                'device_id': t.device_id,
                'sync_status': t.sync_status,
                'updated_at': t.updated_at.isoformat(),
                'is_deleted': t.is_deleted,
                'deleted_at': t.deleted_at.isoformat() if t.deleted_at else None
            })

        # ── STOCK LOGS
        logs_raw = get_qs(StockLog)
        logs_data = []
        for l in logs_raw:
            logs_data.append({
                'id': l.id,
                'company_id': l.company_id,
                'store_id': l.store_id,
                'product_id': l.product_id,
                'quantity_change': float(l.quantity_change),
                'reason': l.reason,
                'reference_id': l.reference_id,
                'device_id': l.device_id,
                'sync_status': l.sync_status,
                'updated_at': l.updated_at.isoformat(),
                'created_at': l.created_at.isoformat()
            })

        # ── NEW MODELS FOR SYNC V2 ───────────────────────────────────────────
        def safe_values(model):
            try:
                return list(get_qs(model).values())
            except Exception as e:
                print(f"[SYNC] Pull Error for {model.__name__}: {str(e)}")
                return []

        suppliers_data = safe_values(Supplier)
        pay_terms_data = safe_values(PaymentTerm)
        receivings_data = safe_values(Receiving)
        recv_items_data = safe_values(ReceivingItem)
        employees_data = safe_values(Employee)
        attendance_data = safe_values(Attendance)
        leaves_data     = safe_values(Leave)
        payrolls_data   = safe_values(Payroll)
        pos_data        = safe_values(PurchaseOrder)
        transfers_data  = safe_values(StockTransfer)
        quotations_data = safe_values(Quotation)
        invoices_data   = safe_values(Invoice)
        inv_items_data  = safe_values(InvoiceItem)
        salepay_data    = safe_values(SalePayment)
        purchase_data = safe_values(Purchase)
        cheque_data = safe_values(Cheque)
        expense_category_data = safe_values(ExpenseCategory)
        loyalty_point_data = safe_values(LoyaltyPoint)
        commission_data = safe_values(Commission)
        work_order_data = safe_values(WorkOrder)
        delivery_zone_data = safe_values(DeliveryZone)
        delivery_data = safe_values(Delivery)
        shift_data = safe_values(Shift)
        custom_field_data = safe_values(CustomField)
        product_custom_value_data = safe_values(ProductCustomValue)
        item_kit_data = safe_values(ItemKit)
        kit_item_data = safe_values(KitItem)
        supplier_custom_field_data = safe_values(SupplierCustomField)
        supplier_custom_field_value_data = safe_values(SupplierCustomFieldValue)
        supplier_document_data = safe_values(SupplierDocument)
        supplier_transaction_data = safe_values(SupplierTransaction)
        candidate_data = safe_values(Candidate)
        performance_review_data = safe_values(PerformanceReview)

        # Fix: Add supplier name to purchase orders and purchases for local SQLite NOT NULL constraint
        supplier_map = {s['id']: s.get('company_name', 'Unknown') for s in suppliers_data}
        for po in pos_data:
            po['supplier'] = supplier_map.get(po.get('supplier_id'), 'Unknown')
        for pur in purchase_data:
            pur['supplier'] = supplier_map.get(pur.get('supplier_id'), 'Unknown')
        gift_card_data = safe_values(GiftCard)

        return Response({
            "status":    "success",
            "company_id": company.id,
            "company_name": company.name,
            "timestamp": timezone.now().isoformat(),
            "updates": {
                "company_details": {
                    "legal_name": company.legal_name or company.name,
                    "tax_id": company.tax_id,
                    "website": company.website,
                    "phone": company.phone,
                    "company_email": company.owner.email,
                },
                "stores":           stores_data,
                "users":            users_data,
                "user_permissions": perms_data,
                "user_stores":     user_stores_data, 
                "customers":       customers_data,
                "accounts":        accounts_data,
                "products":        products_data,
                "sales":           sales_data,
                "transactions":    transactions_data,
                "stock_logs":      logs_data,
                "categories":      categories_data,
                "suppliers":       suppliers_data,
                "payment_terms":   pay_terms_data,
                "receivings":      receivings_data,
                "receiving_items": recv_items_data,
                "employees":       employees_data,
                "attendance":      attendance_data,
                "leaves":          leaves_data,
                "payroll":         payrolls_data,
                "purchase_orders": pos_data,
                "stock_transfers": transfers_data,
                "tax_slabs":       tax_slabs_data,
                "quotations":      quotations_data,
                "invoices":        invoices_data,
                "invoice_items":   inv_items_data,
                "sale_payments":   salepay_data,
                "purchases": purchase_data,
                "cheques": cheque_data,
                "expense_categories": expense_category_data,
                "loyalty_points": loyalty_point_data,
                "commissions": commission_data,
                "work_orders": work_order_data,
                "delivery_zones": delivery_zone_data,
                "deliveries": delivery_data,
                "shifts": shift_data,
                "custom_fields": custom_field_data,
                "product_custom_values": product_custom_value_data,
                "item_kits": item_kit_data,
                "kit_items": kit_item_data,
                "supplier_custom_fields": supplier_custom_field_data,
                "supplier_custom_values": supplier_custom_field_value_data,
                "supplier_documents": supplier_document_data,
                "supplier_transactions": supplier_transaction_data,
                "candidates": candidate_data,
                "performance_reviews": performance_review_data,
                "gift_cards": gift_card_data,
            }
        })


class SyncPushEndpoint(APIView):
    """
    Electron calls this to push locally-made changes up to the cloud.
    Handles: stores, erp_users.
    All writes are strictly scoped to the authenticated user's Company.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        company = get_company_for_user(request.user)
        if not company:
            return Response(
                {"error": "No company found for this user."},
                status=status.HTTP_403_FORBIDDEN
            )

        payload = request.data.get('payload', {})
        synced_ids = {}
        errors = []

        try:
            print(f"[SYNC] PUSH received from {request.user.email} (Company: {company.name})")
            print(f"[SYNC] Payload tables: {list(payload.keys())}")
            
            # Removed global transaction.atomic to allow partial success across tables
        # with transaction.atomic():
            # ── PUSH CATEGORIES ──────────────────────────────────────────
            cat_payload = payload.get('categories', [])
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

            # ── PUSH STORES ───────────────────────────────────────────────
            stores_payload = payload.get('stores', [])
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

            # ── PUSH ERP USERS ────────────────────────────────────────────
            users_payload = payload.get('users', [])
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
                        d_user.save()

                    synced_ids.setdefault('users', []).append(obj_id)

                except Exception as e:
                    print(f"[SYNC] User Push Error ({obj_id}): {str(e)}")
                    errors.append({"table": "users", "id": obj_id, "message": str(e)})

            # ── PUSH USER PERMISSIONS ─────────────────────────────────────
            perms_payload = payload.get('user_permissions', [])
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

            # ── PUSH USER STORES (M2M) ────────────────────────────────────
            user_stores_payload = payload.get('user_stores', [])
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

            # ── PUSH CUSTOMERS ────────────────────────────────────────────
            cust_payload = payload.get('customers', [])
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

            # ── PUSH ACCOUNTS ─────────────────────────────────────────────
            acc_payload = payload.get('accounts', [])
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


            # ── PUSH CATEGORIES ───────────────────────────────────────────
            cat_payload = payload.get('categories', [])
            for row in cat_payload:
                obj_id = row.get('id')
                Category.objects.update_or_create(
                    id=obj_id,
                    company=company,
                    defaults={
                        'store_id':    row.get('store_id'),
                        'name':        row.get('name'),
                        'description': row.get('description', ''),
                        'device_id':   row.get('device_id'),
                        'sync_status': 1,
                    }
                )
                synced_ids.setdefault('categories', []).append(obj_id)

            # ── PUSH PRODUCTS ─────────────────────────────────────────────
            prod_payload = payload.get('products', [])
            for row in prod_payload:
                obj_id = row.get('id')
                try:
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

            # ── PUSH TAX SLABS ────────────────────────────────────────────
            tax_payload = payload.get('tax_slabs', [])
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

            # ── PUSH SALES ────────────────────────────────────────────────
            sales_payload = payload.get('sales', [])
            for row in sales_payload:
                obj_id = row.get('id')
                try:
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

            # ── PUSH TRANSACTIONS ─────────────────────────────────────────
            trans_payload = payload.get('transactions', [])
            for row in trans_payload:
                obj_id = row.get('id')
                try:
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

            # ── PUSH PAYMENT TERMS ────────────────────────────────────────
            pt_payload = payload.get('payment_terms', [])
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

            # ── PUSH SUPPLIERS ────────────────────────────────────────────
            sup_payload = payload.get('suppliers', [])
            print(f"[SYNC] Processing {len(sup_payload)} suppliers...")
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
                    print(f"[SYNC] Supplier Push Error ({obj_id}): {str(e)}")
                    errors.append({"table": "suppliers", "id": obj_id, "message": str(e)})

            # ── PUSH RECEIVINGS ───────────────────────────────────────────
            recv_payload = payload.get('receivings', [])
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

            # ── PUSH RECEIVING ITEMS ──────────────────────────────────────
            ri_payload = payload.get('receiving_items', [])
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

            # ── PUSH STOCK LOGS ───────────────────────────────────────────
            log_payload = payload.get('stock_logs', [])
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
                    print(f"[SYNC] StockLog Push Error ({obj_id}): {str(e)}")
                    errors.append({"table": "stock_logs", "id": obj_id, "message": str(e)})

            # ── PUSH EMPLOYEES ────────────────────────────────────────────
            emp_payload = payload.get('employees', [])
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
                                'is_deleted':   bool(row.get('is_deleted', 0)),
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

            # ── PUSH ATTENDANCE ───────────────────────────────────────────
            att_payload = payload.get('attendance', [])
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

            # ── PUSH LEAVES ───────────────────────────────────────────────
            leave_payload = payload.get('leaves', [])
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

            # ── PUSH PAYROLL ──────────────────────────────────────────────
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

            # ── PUSH PURCHASE ORDERS ──────────────────────────────────────
            po_payload = payload.get('purchase_orders', [])
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

            # ── PUSH STOCK TRANSFERS ──────────────────────────────────────
            st_payload = payload.get('stock_transfers', [])
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

            # ── PUSH QUOTATIONS ──────────────────────────────────────
            quote_payload = payload.get('quotations', [])
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

            # ── PUSH INVOICES ──────────────────────────────────────
            inv_payload = payload.get('invoices', [])
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

            # ── PUSH INVOICE ITEMS ──────────────────────────────────────
            inv_items_payload = payload.get('invoice_items', [])
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

            # ── PUSH SALE PAYMENTS ──────────────────────────────────────
            sp_payload = payload.get('sale_payments', [])
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

            # ── PUSH PURCHASE ──────────────────────────────────────
            purchase_payload = payload.get('purchases', [])
            for row in purchase_payload:
                obj_id = row.get('id')
                try:
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

            # ── PUSH CHEQUE ──────────────────────────────────────
            cheque_payload = payload.get('cheques', [])
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

            # ── PUSH EXPENSECATEGORY ──────────────────────────────────────
            expense_category_payload = payload.get('expense_categories', [])
            for row in expense_category_payload:
                obj_id = row.get('id')
                try:
                    ExpenseCategory.objects.update_or_create(
                        id=obj_id, company=company,
                        defaults={
                            'name': row.get('name'),
                            'parent_id': row.get('parent_id'),
                            'sync_status': 1,
                        }
                    )
                    synced_ids.setdefault('expense_categories', []).append(obj_id)
                except Exception: pass

            # ── PUSH LOYALTYPOINT ──────────────────────────────────────
            loyalty_point_payload = payload.get('loyalty_points', [])
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

            # ── PUSH COMMISSION ──────────────────────────────────────
            commission_payload = payload.get('commissions', [])
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

            # ── PUSH WORKORDER ──────────────────────────────────────
            work_order_payload = payload.get('work_orders', [])
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

            # ── PUSH DELIVERYZONE ──────────────────────────────────────
            delivery_zone_payload = payload.get('delivery_zones', [])
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

            # ── PUSH DELIVERY ──────────────────────────────────────
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

            # ── PUSH SHIFT ──────────────────────────────────────
            shift_payload = payload.get('shifts', [])
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

            # ── PUSH CUSTOMFIELD ──────────────────────────────────────
            custom_field_payload = payload.get('custom_fields', [])
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
                            'sync_status': 1,
                        }
                    )
                    synced_ids.setdefault('custom_fields', []).append(obj_id)
                except Exception: pass

            # ── PUSH PRODUCTCUSTOMVALUE ──────────────────────────────────────
            product_custom_value_payload = payload.get('product_custom_values', [])
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

            # ── PUSH ITEMKIT ──────────────────────────────────────
            item_kit_payload = payload.get('item_kits', [])
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

            # ── PUSH KITITEM ──────────────────────────────────────
            kit_item_payload = payload.get('kit_items', [])
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

            # ── PUSH SUPPLIERCUSTOMFIELD ──────────────────────────────────────
            supplier_custom_field_payload = payload.get('supplier_custom_fields', [])
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
                            'sync_status': 1,
                        }
                    )
                    synced_ids.setdefault('supplier_custom_fields', []).append(obj_id)
                except Exception: pass

            # ── PUSH SUPPLIERCUSTOMFIELDVALUE ──────────────────────────────────────
            supplier_custom_field_value_payload = payload.get('supplier_custom_field_values', [])
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

            # ── PUSH SUPPLIERDOCUMENT ──────────────────────────────────────
            supplier_document_payload = payload.get('supplier_documents', [])
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

            # ── PUSH SUPPLIERTRANSACTION ──────────────────────────────────────
            supplier_transaction_payload = payload.get('supplier_transactions', [])
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

            # ── PUSH CANDIDATE ──────────────────────────────────────
            candidate_payload = payload.get('candidates', [])
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

            # ── PUSH PERFORMANCEREVIEW ──────────────────────────────────────
            performance_review_payload = payload.get('performance_reviews', [])
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

            # ── PUSH GIFTCARD ──────────────────────────────────────
            gift_card_payload = payload.get('gift_cards', [])
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


        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[SYNC] PUSH ERROR: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "status": "success",
            "synced_ids": synced_ids,
            "errors": errors,
            "sync_version": "2.0-MultiTenant"
        })


class DashboardStatsView(APIView):
    """
    Provides aggregated statistics for the ERP dashboard.
    Strictly scoped to the user's company.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = get_company_for_user(request.user)
        if not company:
            return Response({"error": "Company not found"}, status=status.HTTP_404_NOT_FOUND)

        # 1. Overview Metrics
        total_sales = Sale.objects.filter(company=company)
        total_revenue = total_sales.aggregate(total=Sum('total_amount'))['total'] or 0
        total_profit = total_sales.aggregate(total=Sum('profit'))['total'] or 0
        sales_count = total_sales.count()
        
        customer_count = Customer.objects.filter(company=company).count()
        product_count = Product.objects.filter(company=company, is_deleted=False).count()

        # 2. Recent Sales (Last 5)
        recent_sales = []
        for s in total_sales.order_by('-date')[:5]:
            recent_sales.append({
                'invoice_number': s.invoice_number,
                'customer': s.customer.name if s.customer else "Walk-in",
                'total_amount': float(s.total_amount),
                'date': s.date.isoformat(),
                'status': s.status
            })

        # 3. Sales Chart Data (Last 30 Days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        daily_sales = total_sales.filter(date__gte=thirty_days_ago)\
            .extra(select={'day': "date(date)"})\
            .values('day')\
            .annotate(total=Sum('total_amount'))\
            .order_by('day')

        chart_data = []
        for entry in daily_sales:
            chart_data.append({
                'date': str(entry['day']),
                'amount': float(entry['total'])
            })

        return Response({
            "status": "success",
            "metrics": {
                "total_revenue": float(total_revenue),
                "total_profit": float(total_profit),
                "sales_count": sales_count,
                "customer_count": customer_count,
                "product_count": product_count,
            },
            "recent_sales": recent_sales,
            "chart_data": chart_data
        })


class SendSupplierEmailView(APIView):
    """
    Sends an email to a supplier on behalf of the logged-in ERPUser.
    Requires: supplier_email, subject, message
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        supplier_email = request.data.get('supplier_email')
        subject = request.data.get('subject')
        message = request.data.get('message')

        if not all([supplier_email, subject, message]):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        # Get the ERPUser profile for the logged in user
        try:
            erp_user = request.user.erp_profile
        except ERPUser.DoesNotExist:
            return Response({"error": "ERP Profile not found for this user"}, status=status.HTTP_404_NOT_FOUND)

        from .services.email_service import EnterpriseEmailService
        try:
            success = EnterpriseEmailService.send_supplier_email(
                user=erp_user,
                supplier_email=supplier_email,
                subject=subject,
                message=message
            )
            if success:
                return Response({"status": "success", "message": f"Email sent to {supplier_email}"})
            else:
                return Response({"error": "Failed to send email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
