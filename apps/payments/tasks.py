import logging

from celery import shared_task

from apps.payments.models import Invoice
from apps.payments.services.invoice_service import save_invoice_pdf

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
)
def generate_invoice_pdf_task(self, invoice_id):
    """
    Fetch an Invoice by ID, generate its PDF, and save it to the file field.

    Retries up to 3 times with a 60s delay on transient failures.
    """
    try:
        invoice = (
            Invoice.objects.select_related(
                "order__vendor__settings",
            )
            .prefetch_related(
                "order__items__product",
            )
            .get(id=invoice_id)
        )
    except Invoice.DoesNotExist:
        logger.error(
            "generate_invoice_pdf_task: invoice %s not found",
            invoice_id,
        )
        return {"success": False, "error": "Invoice not found"}

    try:
        save_invoice_pdf(invoice)
        logger.info("PDF generated for invoice %s", invoice.invoice_number)
        return {
            "success": True,
            "invoice_id": invoice_id,
            "invoice_number": invoice.invoice_number,
        }
    except Exception as e:
        logger.error(
            "Failed to generate PDF for invoice %s: %s",
            invoice.invoice_number,
            e,
        )
        raise
