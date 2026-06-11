from django.contrib import admin
from .models import (
    ERPUser, Store, ERPUserPermission,
    Category, Product, Customer, Account,
    Sale, Transaction, StockLog, TaxSlab,
    Supplier, PaymentTerm,
    Receiving, ReceivingItem,
    Employee, Attendance, Leave, Payroll,
    PurchaseOrder, StockTransfer,
    Purchase, Quotation, Invoice, InvoiceItem,
    Cheque, SalePayment, ExpenseCategory,
    LoyaltyPoint, Commission,
    WorkOrder, DeliveryZone, Delivery, Shift,
    Setting, UserStore, CustomField, ProductCustomValue,
    ItemKit, KitItem,
    SupplierCustomField, SupplierCustomFieldValue,
    SupplierDocument, SupplierTransaction,
    Candidate, PerformanceReview, GiftCard,
)


# ── CORE ──────────────────────────────────────────────────────────────────────
@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'company', 'device_id', 'sync_status')
    list_filter = ('company',)
    search_fields = ('name', 'branch')

@admin.register(ERPUser)
class ERPUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'role', 'company', 'is_active', 'sync_status')
    list_filter = ('company', 'role', 'is_active')
    search_fields = ('name', 'email', 'username')

@admin.register(ERPUserPermission)
class ERPUserPermissionAdmin(admin.ModelAdmin):
    list_display = ('erp_user', 'updated_at')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'store', 'updated_at')
    list_filter = ('company', 'store')
    search_fields = ('name',)

@admin.register(TaxSlab)
class TaxSlabAdmin(admin.ModelAdmin):
    list_display = ('name', 'percentage', 'company', 'store')
    list_filter = ('company', 'store')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'selling_price', 'quantity', 'company', 'store', 'sync_status')
    list_filter = ('company', 'store', 'category', 'is_deleted')
    search_fields = ('name', 'sku', 'barcode')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'display_balance', 'company', 'store')
    list_filter = ('company', 'store')
    search_fields = ('name', 'phone', 'email')

    def display_balance(self, obj):
        return obj.display_balance
    display_balance.short_description = "Balance (Dr/Cr)"


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'balance', 'company', 'store')
    list_filter = ('company', 'store', 'type')
    search_fields = ('name',)

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'company', 'store', 'total_amount', 'payment_mode', 'status', 'date')
    list_filter = ('company', 'store', 'payment_mode', 'status', 'type')
    search_fields = ('invoice_number',)
    date_hierarchy = 'date'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('type', 'amount', 'description', 'company', 'store', 'date')
    list_filter = ('company', 'store', 'type')
    search_fields = ('description',)

@admin.register(StockLog)
class StockLogAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity_change', 'reason', 'company', 'store', 'created_at')
    list_filter = ('company', 'store', 'reason')

# ── SUPPLIER ──────────────────────────────────────────────────────────────────
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'first_name', 'last_name', 'phone', 'email', 'status', 'company', 'store')
    list_filter = ('company', 'store', 'status', 'currency')
    search_fields = ('company_name', 'first_name', 'last_name', 'phone', 'email', 'supplier_code')

@admin.register(PaymentTerm)
class PaymentTermAdmin(admin.ModelAdmin):
    list_display = ('name', 'days', 'company', 'store')
    list_filter = ('company', 'store')

@admin.register(SupplierCustomField)
class SupplierCustomFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'field_type', 'is_required', 'store')
    list_filter = ('store', 'field_type')

@admin.register(SupplierCustomFieldValue)
class SupplierCustomFieldValueAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'field', 'value')

@admin.register(SupplierDocument)
class SupplierDocumentAdmin(admin.ModelAdmin):
    list_display = ('name', 'supplier', 'file_type', 'uploaded_at', 'store')
    list_filter = ('store', 'file_type')

@admin.register(SupplierTransaction)
class SupplierTransactionAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'type', 'amount', 'balance_after', 'date', 'store')
    list_filter = ('store', 'type', 'status')
    search_fields = ('supplier__company_name', 'reference_id')

# ── RECEIVING ─────────────────────────────────────────────────────────────────
@admin.register(Receiving)
class ReceivingAdmin(admin.ModelAdmin):
    list_display = ('receiving_number', 'supplier', 'total_amount', 'amount_paid', 'status', 'company', 'store')
    list_filter = ('company', 'store', 'status')
    search_fields = ('receiving_number',)

@admin.register(ReceivingItem)
class ReceivingItemAdmin(admin.ModelAdmin):
    list_display = ('receiving', 'product_name', 'quantity', 'cost', 'total', 'company', 'store')
    list_filter = ('company', 'store')
    search_fields = ('product_name',)

# ── HR & PAYROLL ──────────────────────────────────────────────────────────────
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'erp_user', 'designation', 'department', 'salary', 'company', 'store')
    list_filter = ('company', 'store', 'department')
    search_fields = ('erp_user__name', 'designation', 'department', 'user_id')

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'check_in', 'check_out', 'status', 'company', 'store')
    list_filter = ('company', 'store', 'status', 'date')
    date_hierarchy = 'date'

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ('employee', 'type', 'start_date', 'end_date', 'status', 'company', 'store')
    list_filter = ('company', 'store', 'type', 'status')

@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('employee', 'month', 'year', 'net_salary', 'status', 'company', 'store')
    list_filter = ('company', 'store', 'status', 'year', 'month')

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'role', 'status', 'score', 'store')
    list_filter = ('store', 'status')
    search_fields = ('name', 'email', 'role')

@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'review_date', 'rating', 'store')
    list_filter = ('store', 'review_date')

# ── PURCHASE & FINANCE ────────────────────────────────────────────────────────
@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'supplier', 'total_amount', 'status', 'date', 'company', 'store')
    list_filter = ('company', 'store', 'status')
    search_fields = ('po_number',)
    date_hierarchy = 'date'

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'supplier', 'total_amount', 'date', 'company', 'store')
    list_filter = ('company', 'store', 'type')
    search_fields = ('invoice_number',)

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('quotation_number', 'customer_name', 'total_amount', 'status', 'date', 'company', 'store')
    list_filter = ('company', 'store', 'status')
    search_fields = ('quotation_number', 'customer_name')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'type', 'status', 'total_amount', 'amount_due', 'date', 'company', 'store')
    list_filter = ('company', 'store', 'type', 'status')
    search_fields = ('invoice_number',)

@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'description', 'quantity', 'unit_price', 'total', 'company', 'store')
    list_filter = ('company', 'store')

@admin.register(Cheque)
class ChequeAdmin(admin.ModelAdmin):
    list_display = ('cheque_number', 'party_name', 'party_type', 'amount', 'status', 'issue_date', 'company', 'store')
    list_filter = ('company', 'store', 'party_type', 'status')
    search_fields = ('cheque_number', 'party_name', 'bank_name')

@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = ('sale', 'payment_mode', 'amount', 'account')

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_id', 'created_at')
    search_fields = ('name',)

@admin.register(LoyaltyPoint)
class LoyaltyPointAdmin(admin.ModelAdmin):
    list_display = ('customer', 'points', 'reason', 'created_at')
    list_filter = ('customer',)

@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ('erp_user', 'sale_id', 'amount', 'percentage', 'created_at')

# ── LOGISTICS ─────────────────────────────────────────────────────────────────
@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ('id', 'from_store', 'to_store', 'status', 'date', 'company')
    list_filter = ('company', 'status')

@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale', 'status', 'store')
    list_filter = ('store', 'status')

@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'fee', 'is_active', 'store')
    list_filter = ('store', 'is_active')

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale', 'delivery_type', 'status', 'delivery_date', 'store')
    list_filter = ('store', 'status', 'is_cod')
    search_fields = ('tracking_number',)

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('employee', 'type', 'start_time', 'end_time', 'status', 'store')
    list_filter = ('store', 'type', 'status')

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key',)

@admin.register(UserStore)
class UserStoreAdmin(admin.ModelAdmin):
    list_display = ('erp_user', 'store')
    list_filter = ('store',)

@admin.register(CustomField)
class CustomFieldAdmin(admin.ModelAdmin):
    list_display = ('label', 'type', 'target_type', 'is_required', 'show_on_receipt')
    list_filter = ('type', 'target_type')

@admin.register(ProductCustomValue)
class ProductCustomValueAdmin(admin.ModelAdmin):
    list_display = ('product', 'field', 'value')

@admin.register(ItemKit)
class ItemKitAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'selling_price', 'is_active', 'store')
    list_filter = ('store', 'is_active')
    search_fields = ('name', 'sku')

@admin.register(KitItem)
class KitItemAdmin(admin.ModelAdmin):
    list_display = ('kit', 'product', 'quantity')

@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = ('card_number', 'customer', 'value', 'balance', 'is_active', 'store')
    list_filter = ('store', 'is_active')
    search_fields = ('card_number',)
