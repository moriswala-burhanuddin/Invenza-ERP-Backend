import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from django.conf import settings
from datetime import datetime

def generate_invoice_pdf(invoice):
    """
    Generates a professional PDF invoice for a successful payment.
    Returns the file path to the generated PDF.
    """
    invoice_dir = os.path.join(settings.MEDIA_ROOT, 'invoices')
    if not os.path.exists(invoice_dir):
        os.makedirs(invoice_dir)

    filename = f"{invoice.invoice_no}.pdf"
    file_path = os.path.join(invoice_dir, filename)

    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    payment = invoice.payment
    company = payment.company
    subscription = company.subscription

    # Brand Colors
    PRIMARY_COLOR = colors.HexColor("#0071E3")
    DARK_BG = colors.HexColor("#030308")
    TEXT_COLOR = colors.HexColor("#1D1D1F")
    MUTED_COLOR = colors.HexColor("#86868B")
    BG_LIGHT = colors.HexColor("#F5F5F7")

    # Header Background Block
    c.setFillColor(DARK_BG)
    c.rect(0, height - 2 * inch, width, 2 * inch, fill=1, stroke=0)

    # Header Content (White Text)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(1 * inch, height - 1 * inch, "INVENZA ERP")
    
    c.setFont("Helvetica", 11)
    c.drawString(1 * inch, height - 1.25 * inch, "Professional SaaS Solutions")
    c.drawString(1 * inch, height - 1.45 * inch, "support@invenza.erp | www.invenza.erp")

    # Invoice Title
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(width - 1 * inch, height - 1 * inch, "TAX INVOICE")
    
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 1 * inch, height - 1.25 * inch, f"Invoice No: {invoice.invoice_no}")
    date_str = invoice.created_at.strftime('%Y-%m-%d') if invoice.created_at else datetime.now().strftime('%Y-%m-%d')
    c.drawRightString(width - 1 * inch, height - 1.45 * inch, f"Date: {date_str}")

    # Body Starts
    c.setFillColor(TEXT_COLOR)

    # Customer Info Box
    c.setFillColor(BG_LIGHT)
    c.rect(1 * inch, height - 3.8 * inch, (width - 2 * inch) / 2 - 0.2 * inch, 1.3 * inch, fill=1, stroke=0)
    
    c.setFillColor(TEXT_COLOR)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.2 * inch, height - 2.8 * inch, "Bill To:")
    
    c.setFont("Helvetica", 10)
    c.drawString(1.2 * inch, height - 3.1 * inch, company.name)
    c.drawString(1.2 * inch, height - 3.3 * inch, company.owner.email)
    if company.tax_id:
        c.drawString(1.2 * inch, height - 3.5 * inch, f"Tax ID: {company.tax_id}")

    # Payment Info Box
    c.setFillColor(BG_LIGHT)
    c.rect(width / 2 + 0.2 * inch, height - 3.8 * inch, (width - 2 * inch) / 2 - 0.2 * inch, 1.3 * inch, fill=1, stroke=0)
    
    c.setFillColor(TEXT_COLOR)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(width / 2 + 0.4 * inch, height - 2.8 * inch, "Payment Details:")
    
    c.setFont("Helvetica", 10)
    c.drawString(width / 2 + 0.4 * inch, height - 3.1 * inch, f"Status: PAID")
    c.drawString(width / 2 + 0.4 * inch, height - 3.3 * inch, f"Order ID: {payment.razorpay_order_id}")
    c.drawString(width / 2 + 0.4 * inch, height - 3.5 * inch, f"Transaction: {payment.razorpay_payment_id}")

    # Table Header
    table_y = height - 4.5 * inch
    c.setFillColor(DARK_BG)
    c.rect(1 * inch, table_y - 0.25 * inch, width - 2 * inch, 0.4 * inch, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1.2 * inch, table_y - 0.1 * inch, "Description")
    c.drawRightString(width - 1.2 * inch, table_y - 0.1 * inch, "Amount")

    # Table Content
    c.setFillColor(TEXT_COLOR)
    plan_name = subscription.plan.name if hasattr(subscription, 'plan') and subscription.plan else f"Plan ID {payment.plan_id}"
    
    row_y = table_y - 0.7 * inch
    c.setFont("Helvetica", 11)
    c.drawString(1.2 * inch, row_y, f"{plan_name} Subscription Plan")
    c.drawRightString(width - 1.2 * inch, row_y, f"{payment.currency} {invoice.subtotal}")
    
    c.setStrokeColor(colors.HexColor("#E5E5EA"))
    c.line(1 * inch, row_y - 0.2 * inch, width - 1 * inch, row_y - 0.2 * inch)

    # Next Billing Date
    c.setFont("Helvetica", 10)
    c.setFillColor(MUTED_COLOR)
    if hasattr(subscription, 'expiry_date') and subscription.expiry_date:
        c.drawString(1.2 * inch, row_y - 0.5 * inch, f"Next renewal date: {subscription.expiry_date.strftime('%Y-%m-%d')}")

    # Total Section
    total_y = row_y - 1.5 * inch
    c.setFillColor(BG_LIGHT)
    c.rect(width - 3.5 * inch, total_y - 0.2 * inch, 2.5 * inch, 0.8 * inch, fill=1, stroke=0)
    
    c.setFillColor(TEXT_COLOR)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(width - 3.2 * inch, total_y + 0.2 * inch, "TOTAL PAID")
    c.drawRightString(width - 1.3 * inch, total_y + 0.2 * inch, f"{payment.currency} {invoice.total}")

    # Footer
    c.setFillColor(MUTED_COLOR)
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(width / 2, 1.2 * inch, "This is a computer-generated invoice and does not require a physical signature.")
    c.drawCentredString(width / 2, 1 * inch, "Thank you for choosing Invenza ERP!")

    c.save()
    return file_path
