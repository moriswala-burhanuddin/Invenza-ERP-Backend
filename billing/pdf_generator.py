import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from django.conf import settings
from datetime import datetime

def generate_subscription_receipt(subscription):
    """
    Generates a professional PDF receipt for a subscription.
    Returns the file path to the generated PDF.
    """
    receipt_dir = os.path.join(settings.MEDIA_ROOT, 'receipts')
    if not os.path.exists(receipt_dir):
        os.makedirs(receipt_dir)

    filename = f"receipt_{subscription.receipt_number}.pdf"
    file_path = os.path.join(receipt_dir, filename)

    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2, height - 1 * inch, "INVENZA ERP")
    
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, height - 1.25 * inch, "Professional SaaS Solutions")
    c.drawCentredString(width / 2, height - 1.4 * inch, "www.invenza.erp")

    # Receipt Info
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1 * inch, height - 2 * inch, "RECEIPT")
    
    c.setFont("Helvetica", 10)
    c.drawString(1 * inch, height - 2.3 * inch, f"Receipt Number: {subscription.receipt_number}")
    c.drawString(1 * inch, height - 2.5 * inch, f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    c.drawString(1 * inch, height - 2.7 * inch, f"Order ID: {subscription.order_id}")

    # Customer Info
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, height - 3.2 * inch, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(1 * inch, height - 3.4 * inch, f"{subscription.company.name}")
    c.drawString(1 * inch, height - 3.6 * inch, f"Company ID: {subscription.company.id}")

    # Table Header
    c.line(1 * inch, height - 4 * inch, width - 1 * inch, height - 4 * inch)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1.1 * inch, height - 4.2 * inch, "Description")
    c.drawRightString(width - 1.1 * inch, height - 4.2 * inch, "Amount")
    c.line(1 * inch, height - 4.3 * inch, width - 1 * inch, height - 4.3 * inch)

    # Line Item
    c.setFont("Helvetica", 10)
    c.drawString(1.1 * inch, height - 4.6 * inch, f"{subscription.plan.name} Subscription Plan")
    c.drawRightString(width - 1.1 * inch, height - 4.6 * inch, f"INR {subscription.plan.monthly_price}")
    
    # Features
    y_offset = 4.8
    for feature in subscription.features.all():
        c.drawString(1.3 * inch, height - y_offset * inch, f"+ {feature.name}")
        c.drawRightString(width - 1.1 * inch, height - y_offset * inch, f"INR {feature.price}")
        y_offset += 0.2

    # Total
    c.line(width - 3 * inch, height - (y_offset + 0.1) * inch, width - 1 * inch, height - (y_offset + 0.1) * inch)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(width - 3 * inch, height - (y_offset + 0.4) * inch, "TOTAL PAID")
    c.drawRightString(width - 1.1 * inch, height - (y_offset + 0.4) * inch, f"INR {subscription.amount_paid}")

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, 1 * inch, "This is a computer-generated receipt and does not require a signature.")
    c.drawCentredString(width / 2, 0.8 * inch, "Thank you for choosing Invenza ERP!")

    c.save()
    return file_path
