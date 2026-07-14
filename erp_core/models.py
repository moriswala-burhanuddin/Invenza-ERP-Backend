"""
erp_core/models.py
==================
PHASE 2: Core Tenant-Aware ERP Models

KEY RULES:
- Every model has: company = ForeignKey(Company)  <- THE TENANT WALL
- Every model has: updated_at, sync_status          <- FOR SYNC ENGINE
- user owns a company, can have MULTIPLE stores
- Client A's data is 100% invisible to Client B
"""
import random
import string
from django.db import models
from django.contrib.auth import get_user_model
from companies.models import Company

class SyncableModel(models.Model):
    device_id   = models.CharField(max_length=50, null=True, blank=True)
    sync_status = models.IntegerField(default=0)
    is_deleted  = models.BooleanField(default=False)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


DjangoUser = get_user_model()

def generate_id(prefix='id'):
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    return f"{prefix}-{random_str}"

def generate_store_id(): return generate_id('store')
def generate_erp_user_id(): return generate_id('user')
def generate_perm_id(): return generate_id('perm')
def generate_customer_id(): return generate_id('cust')
def generate_product_id(): return generate_id('prod')
def generate_account_id(): return generate_id('acc')
def generate_sale_id(): return generate_id('sale')
def generate_quote_id(): return generate_id('quote')
def generate_pur_id(): return generate_id('pur')
def generate_trans_id(): return generate_id('trans')
def generate_log_id(): return generate_id('log')
def generate_exp_cat_id(): return generate_id('expcat')
def generate_sup_id(): return generate_id('sup')
def generate_scf_id(): return generate_id('scf')
def generate_scfv_id(): return generate_id('scfv')
def generate_stx_id(): return generate_id('stx')
def generate_pt_id(): return generate_id('pt')
def generate_recv_id(): return generate_id('recv')
def generate_ri_id(): return generate_id('ri')
def generate_doc_id(): return generate_id('doc')
def generate_att_id(): return generate_id('att')
def generate_leave_id(): return generate_id('leave')
def generate_payroll_id(): return generate_id('pay')
def generate_perf_id(): return generate_id('perf')
def generate_shift_id(): return generate_id('shift')
def generate_tax_id(): return generate_id('tax')
def generate_st_id(): return generate_id('st')
def generate_po_id(): return generate_id('po')
def generate_lp_id(): return generate_id('lp')
def generate_com_id(): return generate_id('com')
def generate_chq_id(): return generate_id('chq')


# ─────────────────────────────────────────────────────────────────────────────
# STORE  —  A Company can have multiple stores / branches
# ─────────────────────────────────────────────────────────────────────────────
class Store(SyncableModel):
    """
    Represents a physical branch or location owned by a Company (Tenant).
    company_id IS the tenant wall — never expose data across companies.
    """
    id         = models.CharField(max_length=50, primary_key=True, default=generate_store_id)
    company    = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stores')  # TENANT WALL
    name       = models.CharField(max_length=255)
    branch     = models.CharField(max_length=255, null=True, blank=True)
    address    = models.TextField(null=True, blank=True)
    phone      = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return f"[{self.company.name}] {self.name}" + (f" ({self.branch})" if self.branch else "")


# ─────────────────────────────────────────────────────────────────────────────
# ERP USER  —  A user of the desktop ERP application (staff, admin, etc.)
#              Linked to the Company (tenant), can access multiple stores.
# ─────────────────────────────────────────────────────────────────────────────
class ERPUser(SyncableModel):
    """
    Represents a staff member / admin inside the Electron desktop ERP.
    - This is DIFFERENT from the Django website User.
    - A website owner creates their Company -> the owner becomes the first ERPUser (admin).
    - company_id IS the tenant wall — staff of company A cannot see company B data.
    - A user can have access to multiple stores within their company.
    """
    ROLE_CHOICES = [
        ('admin',              'Admin'),
        ('staff',              'Staff'),
        ('hr_manager',         'HR Manager'),
        ('sales_manager',      'Sales Manager'),
        ('inventory_manager',  'Inventory Manager'),
        ('accountant',         'Accountant'),
        ('employee',           'Employee'),
        ('super_admin',        'Super Admin'),
    ]

    id            = models.CharField(max_length=50, primary_key=True, default=generate_erp_user_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='erp_users')  # TENANT WALL
    stores        = models.ManyToManyField(Store, blank=True, related_name='erp_users')  # Multi-store access
    django_user   = models.OneToOneField(DjangoUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='erp_profile')

    # Core Identity
    name          = models.CharField(max_length=255)
    email         = models.EmailField()
    username      = models.CharField(max_length=150)
    password      = models.CharField(max_length=255)  # Hashed — used for Electron local login
    role          = models.CharField(max_length=50, choices=ROLE_CHOICES, default='staff')

    # Profile Fields (matching Electron SQLite schema exactly)
    first_name    = models.CharField(max_length=150, null=True, blank=True, default='')
    last_name     = models.CharField(max_length=150, null=True, blank=True, default='')
    avatar        = models.TextField(null=True, blank=True)
    phone         = models.CharField(max_length=20, null=True, blank=True)
    bio           = models.TextField(null=True, blank=True)
    address_line1 = models.CharField(max_length=255, null=True, blank=True)
    address_line2 = models.CharField(max_length=255, null=True, blank=True)
    city          = models.CharField(max_length=100, null=True, blank=True)
    state         = models.CharField(max_length=100, null=True, blank=True)
    country       = models.CharField(max_length=100, null=True, blank=True)
    pincode       = models.CharField(max_length=20, null=True, blank=True)

    # Flags
    is_active     = models.BooleanField(default=True)
    is_staff      = models.BooleanField(default=False)
    is_driver     = models.BooleanField(default=False)

    # Sync Tracking
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('company', 'email'), ('company', 'username')]  # Scoped within company

    def __str__(self):
        return f"[{self.company.name}] {self.email} ({self.role})"


# ─────────────────────────────────────────────────────────────────────────────
# USER PERMISSION  —  Per-user permission blob (mirrors Electron user_permissions table)
# ─────────────────────────────────────────────────────────────────────────────
class ERPUserPermission(SyncableModel):
    id          = models.CharField(max_length=50, primary_key=True, default=generate_perm_id)
    company     = models.ForeignKey(Company, on_delete=models.CASCADE)  # TENANT WALL
    erp_user    = models.OneToOneField(ERPUser, on_delete=models.CASCADE, related_name='permissions_profile')
    permissions = models.JSONField(default=dict)

    def __str__(self):
        return f"Permissions for {self.erp_user.email}"


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER  —  CRM for the Tenant
# ─────────────────────────────────────────────────────────────────────────────
class Customer(SyncableModel):
    id             = models.CharField(max_length=50, primary_key=True, default=generate_customer_id)
    company        = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='customers')
    store          = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='customers')
    name           = models.CharField(max_length=255)
    phone          = models.CharField(max_length=50)
    email          = models.EmailField(null=True, blank=True)
    area           = models.CharField(max_length=255, null=True, blank=True)
    credit_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Dues (Debit Balance)", help_text="Amount the customer owes. Positive = Dues, Negative = Advance/Credit.")
    
    @property
    def display_balance(self):
        """Returns balance with Dr/Cr notation for Admin/UI."""
        val = self.credit_balance
        if val > 0:
            return f"{val} Dr"
        elif val < 0:
            return f"{abs(val)} Cr"
        return "0.00"

    credit_limit   = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_purchases= models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    source         = models.CharField(max_length=50, default='POS')
    joined_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
    

    def __str__(self):
        return f"[{self.company.name}] {self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT  —  Cash and Bank Accounts per Tenant
# ─────────────────────────────────────────────────────────────────────────────
class Account(SyncableModel):
    TYPES = [
        ('cash', 'Cash'), 
        ('card', 'Card'), 
        ('wallet', 'Wallet'),
        ('bank', 'Bank'),
        ('savings', 'Savings'),
        ('credit', 'Credit')
    ]
    id          = models.CharField(max_length=50, primary_key=True, default=generate_account_id)
    company     = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='accounts')
    store       = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='accounts')
    name        = models.CharField(max_length=255)
    type        = models.CharField(max_length=20, choices=TYPES, default='cash')
    balance     = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
    

    def __str__(self):
        return f"{self.name} ({self.type})"


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT  —  Inventory master filtered by Company
# ─────────────────────────────────────────────────────────────────────────────
from django.utils import timezone

class Category(SyncableModel):
    id = models.CharField(max_length=50, primary_key=True)
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='erp_categories')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='erp_categories')
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

    def __str__(self):
        return f"{self.name} ({self.company.name})"

class TaxSlab(SyncableModel):
    id          = models.CharField(max_length=50, primary_key=True, default=generate_tax_id)
    company     = models.ForeignKey(Company, on_delete=models.CASCADE)
    store       = models.ForeignKey(Store, on_delete=models.CASCADE)
    name        = models.CharField(max_length=100)
    percentage  = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        unique_together = ('company', 'name')
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"

class Product(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_product_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='products')
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='products')
    name             = models.CharField(max_length=255)
    sku              = models.CharField(max_length=100)
    category         = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    selling_price    = models.DecimalField(max_digits=15, decimal_places=2)
    purchase_price   = models.DecimalField(max_digits=15, decimal_places=2)
    quantity         = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    unit             = models.CharField(max_length=50, null=True, blank=True)
    brand            = models.CharField(max_length=100, null=True, blank=True)
    barcode          = models.CharField(max_length=255, null=True, blank=True)
    min_stock        = models.IntegerField(default=0)
    reorder_quantity = models.IntegerField(default=0)
    
    # Legacy compatibility fields (can be deprecated later)
    category_name      = models.CharField(max_length=255, null=True, blank=True)
    categoryId         = models.CharField(max_length=50, null=True, blank=True)
    categoryName       = models.CharField(max_length=255, null=True, blank=True)
    barcode_enabled    = models.BooleanField(default=1)
    last_used          = models.DateTimeField(null=True, blank=True)
    limited_qty        = models.BooleanField(default=0)
    is_kit           = models.BooleanField(default=False)
    is_serialized    = models.BooleanField(default=False)
    tax_slab         = models.ForeignKey(TaxSlab, on_delete=models.SET_NULL, null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    price_inr        = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_usd        = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    

    def __str__(self):
        return f"[{self.company.name}] {self.name}"

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]


# ─────────────────────────────────────────────────────────────────────────────
# SALE  —  Invoice data
# ─────────────────────────────────────────────────────────────────────────────
class Sale(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_sale_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='sales', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sales')
    customer         = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True)
    account          = models.ForeignKey(Account, on_delete=models.PROTECT)
    
    invoice_number   = models.CharField(max_length=100)
    type             = models.CharField(max_length=50, default='retail')
    status           = models.CharField(max_length=50, default='completed')
    items            = models.JSONField() # Professional JSON storage
    subtotal         = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount  = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tax_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_amount     = models.DecimalField(max_digits=15, decimal_places=2)
    
    original_amount  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    original_currency= models.CharField(max_length=10, null=True, blank=True)
    
    profit           = models.DecimalField(max_digits=15, decimal_places=2)
    payment_mode     = models.CharField(max_length=50)
    source           = models.CharField(max_length=50, default='POS')
    date             = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['company', 'invoice_number'], name='unique_company_sale_invoice')
        ]
    

    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.total_amount})"


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTION  —  Cash flow (In / Out / Expense)
# ─────────────────────────────────────────────────────────────────────────────
class Transaction(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_trans_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='transactions')
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='transactions')
    account          = models.ForeignKey(Account, on_delete=models.CASCADE)
    customer         = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    expense_category = models.ForeignKey('ExpenseCategory', on_delete=models.SET_NULL, null=True, blank=True)
    
    type             = models.CharField(max_length=50) # cash_in, cash_out, expense
    amount           = models.DecimalField(max_digits=15, decimal_places=2)
    description      = models.TextField(null=True, blank=True)
    date             = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
    


# ─────────────────────────────────────────────────────────────────────────────
# STOCK LOG  —  Audit trail for inventory
# ─────────────────────────────────────────────────────────────────────────────
class StockLog(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_log_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_logs', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='stock_logs')
    product          = models.ForeignKey(Product, on_delete=models.CASCADE)
    
    quantity_change  = models.DecimalField(max_digits=15, decimal_places=2)
    reason           = models.CharField(max_length=255)
    reference_id     = models.CharField(max_length=50, null=True, blank=True)
    
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]


# ─────────────────────────────────────────────────────────────────────────────
# SUPPLIER & PROCUREMENT
# ─────────────────────────────────────────────────────────────────────────────
class PaymentTerm(SyncableModel):
    id          = models.CharField(max_length=50, primary_key=True, default=generate_pt_id)
    company     = models.ForeignKey(Company, on_delete=models.CASCADE)
    store       = models.ForeignKey(Store, on_delete=models.CASCADE)
    name        = models.CharField(max_length=100)
    days        = models.IntegerField(default=0)

    def __str__(self):
        return self.name

class Supplier(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_sup_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='suppliers')
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='suppliers')
    
    supplier_code    = models.CharField(max_length=50, null=True, blank=True)
    company_name     = models.CharField(max_length=255)
    first_name       = models.CharField(max_length=255, null=True, blank=True)
    last_name        = models.CharField(max_length=255, null=True, blank=True)
    email            = models.EmailField(max_length=255, null=True, blank=True)
    phone            = models.CharField(max_length=50, null=True, blank=True)
    website          = models.URLField(max_length=255, null=True, blank=True)
    
    address_line1    = models.TextField(null=True, blank=True)
    address_line2    = models.TextField(null=True, blank=True)
    city             = models.CharField(max_length=100, null=True, blank=True)
    state            = models.CharField(max_length=100, null=True, blank=True)
    zip_code         = models.CharField(max_length=20, null=True, blank=True)
    country          = models.CharField(max_length=100, null=True, blank=True)
    
    account_number   = models.CharField(max_length=100, null=True, blank=True)
    opening_balance  = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    payment_term     = models.ForeignKey(PaymentTerm, on_delete=models.SET_NULL, null=True, blank=True)
    credit_limit     = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tax_number       = models.CharField(max_length=100, null=True, blank=True)
    currency         = models.CharField(max_length=10, default='USD')
    current_balance  = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    internal_notes   = models.TextField(null=True, blank=True)
    comments         = models.TextField(null=True, blank=True)
    logo             = models.TextField(null=True, blank=True) # URL or Base64
    documents        = models.JSONField(null=True, blank=True) # JSON list of URLs
    
    status           = models.CharField(max_length=50, default='active')
    rating           = models.IntegerField(default=5)
    is_preferred     = models.BooleanField(default=False)
    is_blacklisted   = models.BooleanField(default=False)
    

    def __str__(self):
        return f"[{self.company.name}] {self.company_name}"


# ─────────────────────────────────────────────────────────────────────────────
# RECEIVING MODULE
# ─────────────────────────────────────────────────────────────────────────────
class Receiving(SyncableModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('suspended', 'Suspended'),
        ('completed', 'Completed'),
        ('returned', 'Returned'),
    ]
    id               = models.CharField(max_length=50, primary_key=True, default=generate_recv_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='receivings')
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='receivings')
    receiving_number = models.CharField(max_length=100) # Removed unique=True
    supplier         = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='receivings')
    purchase_order_id= models.CharField(max_length=50, null=True, blank=True)
    total_amount     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_due       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    original_amount  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    original_currency= models.CharField(max_length=10, null=True, blank=True)
    
    account          = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='receivings')
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes            = models.TextField(null=True, blank=True)
    custom_fields    = models.JSONField(null=True, blank=True)
    completed_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['company', 'receiving_number'], name='unique_company_receiving_number')
        ]

    def __str__(self):
        return f"Receiving {self.receiving_number}"

class ReceivingItem(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='receiving_items', null=True, blank=True)
    store         = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='receiving_items', null=True, blank=True)
    receiving     = models.ForeignKey(Receiving, on_delete=models.CASCADE, related_name='items')
    product       = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name  = models.CharField(max_length=255)
    cost          = models.DecimalField(max_digits=12, decimal_places=2)
    quantity      = models.DecimalField(max_digits=12, decimal_places=3)
    discount_pct  = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total         = models.DecimalField(max_digits=12, decimal_places=2)
    batch_number  = models.CharField(max_length=100, null=True, blank=True)
    expiry_date   = models.DateField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, null=True, blank=True)
    location      = models.CharField(max_length=100, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    upc           = models.CharField(max_length=100, null=True, blank=True)
    description   = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]


# ─────────────────────────────────────────────────────────────────────────────
# HR & PAYROLL
# ─────────────────────────────────────────────────────────────────────────────
class Employee(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_erp_user_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees')
    store         = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='employees')
    erp_user      = models.OneToOneField(ERPUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_profile')
    user_id       = models.CharField(max_length=50, null=True, blank=True)
    
    # Redundant fields for sync reliability & Admin visibility
    name          = models.CharField(max_length=255, null=True, blank=True)
    email         = models.EmailField(null=True, blank=True)

    department    = models.CharField(max_length=100, null=True, blank=True)
    designation   = models.CharField(max_length=100, null=True, blank=True)
    salary        = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    joining_date  = models.DateField(null=True, blank=True)
    documents     = models.JSONField(null=True, blank=True)

    is_verified   = models.BooleanField(default=False)

    def __str__(self):
        name = self.name or (self.erp_user.name if self.erp_user_id else self.user_id or self.id)
        return f"{name} ({self.designation or 'Employee'})"

class Attendance(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_att_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store         = models.ForeignKey(Store, on_delete=models.CASCADE, null=True, blank=True)
    employee      = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance')
    date          = models.DateField()
    check_in      = models.TimeField(null=True, blank=True)
    check_out     = models.TimeField(null=True, blank=True)
    status        = models.CharField(max_length=50, default='present') # present, absent, late, half_day


class Leave(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_leave_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='leaves')
    store         = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='leaves')
    employee      = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leaves')
    
    type          = models.CharField(max_length=50) # sick, casual, privilege
    start_date    = models.DateField()
    end_date      = models.DateField()
    reason        = models.TextField(null=True, blank=True)
    status        = models.CharField(max_length=50, default='pending') # pending, approved, rejected
    

class Payroll(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_payroll_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payrolls')
    store         = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='payrolls')
    employee      = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    
    month         = models.IntegerField()
    year          = models.IntegerField()
    basic_salary  = models.DecimalField(max_digits=15, decimal_places=2)
    allowances    = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    deductions    = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_salary    = models.DecimalField(max_digits=15, decimal_places=2)
    
    status        = models.CharField(max_length=50, default='pending') # pending, paid
    payment_date  = models.DateField(null=True, blank=True)
    paid_at       = models.DateTimeField(null=True, blank=True)

class PurchaseOrder(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_po_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_orders')
    store         = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='purchase_orders')
    po_number     = models.CharField(max_length=100)
    supplier      = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    
    total_amount  = models.DecimalField(max_digits=15, decimal_places=2)
    status        = models.CharField(max_length=50, default='draft') # draft, sent, received
    items         = models.JSONField() # Detailed items list
    date          = models.DateField()

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
    

class StockTransfer(SyncableModel):
    id            = models.CharField(max_length=50, primary_key=True, default=generate_st_id)
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_transfers')
    from_store    = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='transfers_out')
    to_store      = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='transfers_in')
    
    status        = models.CharField(max_length=50, default='pending') # pending, in_transit, completed
    items         = models.JSONField()
    product_id    = models.CharField(max_length=50, null=True, blank=True)
    quantity      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    transferred_at= models.DateTimeField(null=True, blank=True)
    date          = models.DateField()
    


# ─────────────────────────────────────────────────────────────────────────────
# NEW FINANCIAL & SALES MODELS
# ─────────────────────────────────────────────────────────────────────────────
class Purchase(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_pur_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchases', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='purchases')
    supplier         = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    account          = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    
    invoice_number   = models.CharField(max_length=100)
    type             = models.CharField(max_length=50, default='standard')
    items            = models.JSONField(default=list)
    total_amount     = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    original_amount  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    original_currency= models.CharField(max_length=10, null=True, blank=True)
    
    date             = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['company', 'invoice_number'], name='unique_company_purchase_invoice')
        ]

class Quotation(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_quote_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='quotations')
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='quotations')
    customer         = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    
    quotation_number = models.CharField(max_length=100)
    items            = models.JSONField(default=list)
    total_amount     = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    customer_name    = models.CharField(max_length=255, null=True, blank=True)
    customer_phone   = models.CharField(max_length=50, null=True, blank=True)
    date             = models.DateTimeField()
    expiry_date      = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=50, default='pending')
    notes            = models.TextField(null=True, blank=True)

    original_amount   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'quotation_number'], 
                name='unique_company_quotation_number',
                condition=models.Q(is_deleted=False)
            )
        ]

class Invoice(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    customer         = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    supplier         = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    
    invoice_number   = models.CharField(max_length=100)
    type             = models.CharField(max_length=50, default='sales')
    status           = models.CharField(max_length=50, default='unpaid')
    
    date             = models.DateField()
    due_date         = models.DateField(null=True, blank=True)
    
    subtotal         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount  = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount     = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    amount_paid      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    amount_due       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    original_amount  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    original_currency= models.CharField(max_length=10, null=True, blank=True)
    
    notes            = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['company', 'invoice_number'], name='unique_company_invoice_number')
        ]

class InvoiceItem(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, null=True, blank=True)
    invoice          = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    product          = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    
    description      = models.CharField(max_length=255)
    quantity         = models.DecimalField(max_digits=15, decimal_places=2, default=1)
    unit_price       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount  = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total            = models.DecimalField(max_digits=15, decimal_places=2, default=0)

class Cheque(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_chq_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cheques', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='cheques', null=True, blank=True)
    
    party_type       = models.CharField(max_length=50) # 'customer' or 'supplier'
    party_id         = models.CharField(max_length=50)
    party_name       = models.CharField(max_length=255)
    
    cheque_number    = models.CharField(max_length=100)
    bank_name        = models.CharField(max_length=255)
    amount           = models.DecimalField(max_digits=15, decimal_places=2)
    issue_date       = models.DateField()
    clearing_date    = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=50, default='pending')
    notes            = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'bank_name', 'cheque_number'], 
                name='unique_cheque_per_company'
            )
        ]

class SalePayment(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='sale_payments_core', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sale_payments_core', null=True, blank=True)
    sale             = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    account          = models.ForeignKey(Account, on_delete=models.CASCADE)
    payment_mode     = models.CharField(max_length=50)
    amount           = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class ExpenseCategory(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_exp_cat_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='expense_categories', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='expense_categories', null=True, blank=True)
    name             = models.CharField(max_length=255)
    parent_id        = models.CharField(max_length=50, null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class LoyaltyPoint(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_lp_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='loyalty_points', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='loyalty_points', null=True, blank=True)
    customer         = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='loyalty_points_history')
    points           = models.IntegerField(default=0)
    reason           = models.CharField(max_length=255)
    sale_id          = models.CharField(max_length=50, null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class Commission(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_com_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='commissions', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='commissions', null=True, blank=True)
    erp_user         = models.ForeignKey(ERPUser, on_delete=models.CASCADE)
    sale_id          = models.CharField(max_length=50)
    amount           = models.DecimalField(max_digits=15, decimal_places=2)
    percentage       = models.DecimalField(max_digits=5, decimal_places=2)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]


# ─────────────────────────────────────────────────────────────────────────────
# LOGISTICS & OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────
class WorkOrder(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    sale             = models.ForeignKey(Sale, on_delete=models.CASCADE)
    status           = models.CharField(max_length=50, default='pending')
    notes            = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class DeliveryZone(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, null=True, blank=True)
    name             = models.CharField(max_length=255)
    fee              = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active        = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class Delivery(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    sale             = models.ForeignKey(Sale, on_delete=models.CASCADE)
    employee         = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    
    delivery_provider= models.CharField(max_length=255, null=True, blank=True)
    tracking_number  = models.CharField(max_length=255, null=True, blank=True)
    delivery_type    = models.CharField(max_length=100, null=True, blank=True)
    address          = models.TextField()
    delivery_charge  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_cod           = models.BooleanField(default=False)
    status           = models.CharField(max_length=50, default='pending')
    delivery_date    = models.DateField(null=True, blank=True)
    notes            = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class Shift(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_shift_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    employee         = models.ForeignKey(Employee, on_delete=models.CASCADE)
    start_time       = models.DateTimeField()
    end_time         = models.DateTimeField(null=True, blank=True)
    type             = models.CharField(max_length=50) # morning, evening, night
    status           = models.CharField(max_length=50, default='scheduled')

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION & ECOSYSTEM EXTENSIONS
# ─────────────────────────────────────────────────────────────────────────────
class Setting(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    key              = models.CharField(max_length=255)
    value            = models.TextField()

class UserStore(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    erp_user         = models.ForeignKey(ERPUser, on_delete=models.CASCADE)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)

class CustomField(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='custom_fields', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='custom_fields', null=True, blank=True)
    label            = models.CharField(max_length=255)
    type             = models.CharField(max_length=50) # text, number, date, select
    options          = models.JSONField(null=True, blank=True) # For choices
    is_required      = models.BooleanField(default=False)
    show_on_receipt  = models.BooleanField(default=False)
    target_type      = models.CharField(max_length=50) # product, client, sale, employee
    is_deleted       = models.BooleanField(default=False)
    deleted_at       = models.DateTimeField(null=True, blank=True)
    device_id        = models.CharField(max_length=100, null=True, blank=True)
    updated_at       = models.DateTimeField(auto_now=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store', 'target_type']),
        ]
        unique_together = ['company', 'label', 'target_type']

class ProductCustomValue(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='product_custom_values', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='product_custom_values', null=True, blank=True)
    product          = models.ForeignKey(Product, on_delete=models.CASCADE)
    field            = models.ForeignKey(CustomField, on_delete=models.CASCADE)
    value            = models.TextField()
    is_deleted       = models.BooleanField(default=False)
    deleted_at       = models.DateTimeField(null=True, blank=True)
    device_id        = models.CharField(max_length=100, null=True, blank=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store', 'product']),
        ]

class SaleCustomValue(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='sale_custom_values', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sale_custom_values', null=True, blank=True)
    sale             = models.ForeignKey(Sale, on_delete=models.CASCADE)
    field            = models.ForeignKey(CustomField, on_delete=models.CASCADE)
    value            = models.TextField()
    is_deleted       = models.BooleanField(default=False)
    deleted_at       = models.DateTimeField(null=True, blank=True)
    device_id        = models.CharField(max_length=100, null=True, blank=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store', 'sale']),
        ]

class ItemKit(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    name             = models.CharField(max_length=255)
    sku              = models.CharField(max_length=100)
    category         = models.CharField(max_length=100, null=True, blank=True)
    selling_price    = models.DecimalField(max_digits=15, decimal_places=2)
    is_active        = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class KitItem(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='kit_items', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='kit_items', null=True, blank=True)
    kit              = models.ForeignKey(ItemKit, on_delete=models.CASCADE)
    product          = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity         = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class SupplierCustomField(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supplier_custom_fields', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    name             = models.CharField(max_length=255)
    field_type       = models.CharField(max_length=50)
    is_required      = models.BooleanField(default=False)
    show_on_receipt  = models.BooleanField(default=False)
    hide_label       = models.BooleanField(default=False)
    options          = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class SupplierCustomFieldValue(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supplier_custom_values', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='supplier_custom_values', null=True, blank=True)
    supplier         = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    field            = models.ForeignKey(SupplierCustomField, on_delete=models.CASCADE)
    value            = models.TextField()

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class SupplierDocument(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supplier_documents', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    supplier         = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    name             = models.CharField(max_length=255)
    file_path        = models.CharField(max_length=500)
    file_type        = models.CharField(max_length=50)
    uploaded_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class SupplierTransaction(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supplier_transactions', null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='supplier_transactions')
    supplier         = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    type             = models.CharField(max_length=50)
    amount           = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after    = models.DecimalField(max_digits=15, decimal_places=2)
    date             = models.DateTimeField()
    reference_id     = models.CharField(max_length=100, null=True, blank=True)
    description      = models.TextField(null=True, blank=True)
    status           = models.CharField(max_length=50, default='completed')

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class Candidate(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    name             = models.CharField(max_length=255)
    email            = models.EmailField()
    phone            = models.CharField(max_length=50, null=True, blank=True)
    role             = models.CharField(max_length=100)
    status           = models.CharField(max_length=50, default='applied')
    resume_text      = models.TextField(null=True, blank=True)
    score            = models.IntegerField(default=0)
    skills           = models.JSONField(default=list)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class PerformanceReview(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_perf_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    employee         = models.ForeignKey(Employee, on_delete=models.CASCADE)
    review_date      = models.DateField()
    reviewer_id      = models.CharField(max_length=50)
    rating           = models.DecimalField(max_digits=3, decimal_places=1)
    comments         = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class GiftCard(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    store            = models.ForeignKey(Store, on_delete=models.CASCADE)
    customer         = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    card_number      = models.CharField(max_length=100)
    value            = models.DecimalField(max_digits=15, decimal_places=2)
    balance          = models.DecimalField(max_digits=15, decimal_places=2)
    is_active        = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'store']),
        ]

class CurrencyRate(SyncableModel):
    id               = models.CharField(max_length=50, primary_key=True, default=generate_id)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='currency_rates', null=True, blank=True)
    currency_code    = models.CharField(max_length=10) # USD, UGX, GBP, INR
    rate             = models.DecimalField(max_digits=15, decimal_places=6, default=1.0)
    is_active        = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'currency_code']),
        ]
        unique_together = ('company', 'currency_code')

    def __str__(self):
        return f"{self.currency_code} - {self.rate}"
