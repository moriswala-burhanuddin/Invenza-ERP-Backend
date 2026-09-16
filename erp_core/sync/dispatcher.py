from .handlers import *

PUSH_HANDLERS = {
    'suppliers': handle_suppliers,
    'stock_logs': handle_stock_logs,
    'categories': handle_categories,
    'stores': handle_stores,
    'users': handle_users,
    'user_permissions': handle_user_permissions,
    'user_stores': handle_user_stores,
    'customers': handle_customers,
    'accounts': handle_accounts,
    'products': handle_products,
    'tax_slabs': handle_tax_slabs,
    'sales': handle_sales,
    'transactions': handle_transactions,
    'payment_terms': handle_payment_terms,
    'receivings': handle_receivings,
    'receiving_items': handle_receiving_items,
    'employees': handle_employees,
    'attendance': handle_attendance,
    'leaves': handle_leaves,
    'payroll': handle_payroll,
    'purchase_orders': handle_purchase_orders,
    'stock_transfers': handle_stock_transfers,
    'quotations': handle_quotations,
    'invoices': handle_invoices,
    'invoice_items': handle_invoice_items,
    'sale_payments': handle_sale_payments,
    'purchases': handle_purchases,
    'cheques': handle_cheques,
    'expense_categories': handle_expense_categories,
    'loyalty_points': handle_loyalty_points,
    'commissions': handle_commissions,
    'work_orders': handle_work_orders,
    'delivery_zones': handle_delivery_zones,
    'deliveries': handle_deliveries,
    'shifts': handle_shifts,
    'custom_fields': handle_custom_fields,
    'product_custom_values': handle_product_custom_values,
    'item_kits': handle_item_kits,
    'kit_items': handle_kit_items,
    'supplier_custom_fields': handle_supplier_custom_fields,
    'supplier_custom_values': handle_supplier_custom_values,
    'supplier_documents': handle_supplier_documents,
    'supplier_transactions': handle_supplier_transactions,
    'candidates': handle_candidates,
    'performance_reviews': handle_performance_reviews,
    'gift_cards': handle_gift_cards,
}

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
