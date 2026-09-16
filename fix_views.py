import sys
import re

views_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\views.py'
handlers_path = r'd:\paid-erp\invenza-erp\invenza-website\backend\erp_core\sync\handlers.py'

# 1. Append the missing views to views.py
extra_views = '''

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
        daily_sales = total_sales.filter(date__gte=thirty_days_ago)\\
            .extra(select={'day': "date(date)"})\\
            .values('day')\\
            .annotate(total=Sum('total_amount'))\\
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
'''
with open(views_path, 'r', encoding='utf-8') as f:
    if 'class DashboardStatsView' not in f.read():
        with open(views_path, 'a', encoding='utf-8') as fa:
            fa.write(extra_views)
            print("Appended views to views.py")

# 2. Append handle_suppliers and handle_stock_logs to handlers.py
missing_handlers = '''
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
'''
with open(handlers_path, 'r', encoding='utf-8') as f:
    if 'def handle_suppliers' not in f.read():
        with open(handlers_path, 'a', encoding='utf-8') as fa:
            fa.write(missing_handlers)
            print("Appended handle_suppliers to handlers.py")
