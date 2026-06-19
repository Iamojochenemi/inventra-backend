from django.utils import timezone
from django.core.files.base import ContentFile
from apps.payments.models import Invoice
from io import BytesIO
import logging
import json
from datetime import timedelta

logger = logging.getLogger(__name__)

def create_invoice_from_order(order, notes=""):
    """
    Create an invoice from an order.
    
    Args:
        order: Order instance
        notes: Optional invoice notes
        
    Returns:
        Invoice instance
    """
    try:
        # Check if invoice already exists
        if hasattr(order, 'invoice'):
            return order.invoice
        
        # Generate invoice number (format: INV-YYYY-MM-DD-ID)
        invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-{order.id}"
        
        # Create invoice
        invoice = Invoice.objects.create(
            order=order,
            invoice_number=invoice_number,
            status="issued",
            amount=order.total_amount,
            currency=order.vendor.settings.currency if hasattr(order.vendor, 'settings') else "NGN",
            issued_at=timezone.now(),
            due_date=timezone.now() + timedelta(days=7),
            notes=notes,
        )
        
        logger.info(f"Invoice {invoice_number} created for order {order.id}")
        return invoice
        
    except Exception as e:
        logger.error(f"Failed to create invoice for order {order.id}: {str(e)}")
        raise

def generate_invoice_pdf(invoice):
    """
    Generate PDF for invoice using ReportLab.
    
    Args:
        invoice: Invoice instance
        
    Returns:
        BytesIO object with PDF content
    """
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        # Create PDF buffer
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=1,  # Center
        )
        story.append(Paragraph("INVOICE", title_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Invoice details
        details = [
            ['Invoice Number:', invoice.invoice_number],
            ['Invoice Date:', invoice.issued_at.strftime('%Y-%m-%d') if invoice.issued_at else 'N/A'],
            ['Due Date:', invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else 'N/A'],
            ['Status:', invoice.get_status_display()],
        ]
        
        details_table = Table(details, colWidths=[2 * inch, 3 * inch])
        details_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(details_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Order and vendor info
        vendor = invoice.order.vendor
        order_info = [
            ['Vendor:', vendor.name],
            ['Order ID:', f"#{invoice.order.id}"],
            ['Customer:', invoice.order.customer_name],
            ['Phone:', invoice.order.customer_phone or 'N/A'],
        ]
        
        order_table = Table(order_info, colWidths=[2 * inch, 3 * inch])
        order_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(order_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Order items
        items_data = [['Product', 'Quantity', 'Unit Price', 'Total']]
        for item in invoice.order.items.all():
            items_data.append([
                item.product.name,
                str(item.quantity),
                f"{item.unit_price:,.2f}",
                f"{item.quantity * item.unit_price:,.2f}",
            ])
        
        items_table = Table(items_data, colWidths=[2.5 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Total
        total_style = ParagraphStyle(
            'Total',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#e74c3c'),
            alignment=2,  # Right
        )
        story.append(Paragraph(
            f"<b>Total: {invoice.currency} {invoice.amount:,.2f}</b>",
            total_style
        ))
        
        # Notes
        if invoice.notes:
            story.append(Spacer(1, 0.3 * inch))
            notes_style = ParagraphStyle(
                'Notes',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.grey,
            )
            story.append(Paragraph("<b>Notes:</b>", styles['Heading3']))
            story.append(Paragraph(invoice.notes, notes_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        logger.info(f"PDF generated for invoice {invoice.invoice_number}")
        return buffer
        
    except Exception as e:
        logger.error(f"Failed to generate PDF for invoice {invoice.id}: {str(e)}")
        raise

def save_invoice_pdf(invoice):
    """
    Generate and save PDF for invoice.
    
    Args:
        invoice: Invoice instance
    """
    try:
        pdf_buffer = generate_invoice_pdf(invoice)
        filename = f"{invoice.invoice_number}.pdf"
        
        invoice.pdf_file.save(
            filename,
            ContentFile(pdf_buffer.getvalue()),
            save=True
        )
        
        logger.info(f"PDF saved for invoice {invoice.invoice_number}")
        
    except Exception as e:
        logger.error(f"Failed to save PDF for invoice {invoice.id}: {str(e)}")
        raise

def mark_invoice_as_paid(invoice):
    """
    Mark invoice as paid.
    
    Args:
        invoice: Invoice instance
    """
    invoice.status = "paid"
    invoice.paid_at = timezone.now()
    invoice.save()
    
    logger.info(f"Invoice {invoice.invoice_number} marked as paid")
    return invoice

def mark_invoice_as_overdue(invoice):
    """
    Mark invoice as overdue if past due date.
    
    Args:
        invoice: Invoice instance
    """
    if invoice.due_date and timezone.now() > invoice.due_date and invoice.status not in ["paid", "cancelled"]:
        invoice.status = "overdue"
        invoice.save()
        logger.info(f"Invoice {invoice.invoice_number} marked as overdue")
    
    return invoice