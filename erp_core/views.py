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
            
        if company.subscription_status == 'expired':
            return Response(
                {"error": "SUBSCRIPTION_EXPIRED", "detail": "Your subscription has expired. Please renew to continue syncing data."},
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
            else:
                # Full sync (fresh login): skip deleted records — client starts empty
                # For incremental syncs (last_sync exists), we still send deleted records
                # so the client can mark them as deleted locally.
                if hasattr(model, 'is_deleted'):
                    qs = qs.filter(is_deleted=False)
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


from .sync.dispatcher import SyncDispatcher
from .sync.utils import get_company_for_user

class SyncPushEndpoint(APIView):
    """
    Electron calls this to push locally-made changes up to the cloud.
    Delegates all processing to SyncDispatcher.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        company = get_company_for_user(request.user)
        if not company:
            return Response(
                {"error": "No company found for this user."},
                status=status.HTTP_403_FORBIDDEN
            )

        if company.subscription_status == 'expired':
            return Response(
                {"error": "SUBSCRIPTION_EXPIRED", "detail": "Your subscription has expired. Please renew to continue syncing data."},
                status=status.HTTP_403_FORBIDDEN
            )

        payload = request.data.get('payload', {})
        print(f"[SYNC] PUSH received from {request.user.email} (Company: {company.name})")
        print(f"[SYNC] Payload tables: {list(payload.keys())}")
        
        result = SyncDispatcher.dispatch_push(payload, company)
        return Response(result, status=status.HTTP_200_OK)


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
