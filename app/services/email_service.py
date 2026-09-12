"""
Email Service - async invoice email with SMTP + development fallback to console log.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict

logger = logging.getLogger(__name__)


def _format_invoice_text(bill_data: Dict) -> str:
    """Plain text fallback invoice."""
    lines = []
    lines.append("=" * 60)
    lines.append("                    INVOICE")
    lines.append("=" * 60)
    lines.append(f"Bill Number    : {bill_data.get('bill_number')}")
    lines.append(f"Customer Email : {bill_data.get('customer_email')}")
    lines.append(f"Date           : {bill_data.get('created_at')}")
    lines.append("-" * 60)
    lines.append("Items:")
    for item in bill_data.get("items", []):
        lines.append(
            f"  {item.get('product_id')} | {item.get('product_name')} | "
            f"{item.get('quantity')} x {item.get('unit_price'):.2f} = {item.get('purchase_price'):.2f} "
            f"+ Tax {item.get('tax_payable'):.2f} => {item.get('total_price'):.2f}"
        )
    lines.append("-" * 60)
    lines.append(f"Total without tax        : {bill_data.get('total_without_tax'):.2f}")
    lines.append(f"Total tax payable        : {bill_data.get('total_tax_payable'):.2f}")
    lines.append(f"Net price                : {bill_data.get('net_price'):.2f}")
    lines.append(f"Rounded down net price   : {bill_data.get('rounded_down_net_price'):.2f}")
    lines.append(f"Cash paid                : {bill_data.get('cash_paid'):.2f}")
    lines.append(f"Balance payable          : {bill_data.get('balance_payable'):.2f}")
    lines.append(f"Denominations returned   : {bill_data.get('denominations_returned')}")
    lines.append("=" * 60)
    lines.append("Thank you for shopping with us!")
    lines.append("=" * 60)
    return "\n".join(lines)


def _format_invoice_html(bill_data: Dict) -> str:
    """HTML invoice for email."""
    items_rows = ""
    for item in bill_data.get("items", []):
        items_rows += f"""
        <tr>
            <td style="padding:8px; border:1px solid #ddd;">{item.get('product_id')}</td>
            <td style="padding:8px; border:1px solid #ddd;">{item.get('product_name')}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{item.get('unit_price'):.2f}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:center;">{item.get('quantity')}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{item.get('purchase_price'):.2f}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:center;">{item.get('tax_percentage'):.1f}%</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{item.get('tax_payable'):.2f}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right; font-weight:bold;">{item.get('total_price'):.2f}</td>
        </tr>
        """

    denom = bill_data.get("denominations_returned", "{}")
    # beautify denominations if string
    denom_str = str(denom)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color:#333; max-width:700px; margin:auto;">
        <div style="border:2px solid #2c3e50; padding:20px; border-radius:8px;">
            <h2 style="text-align:center; color:#2c3e50; margin-bottom:5px;">INVOICE</h2>
            <p style="text-align:center; color:#777; margin-top:0;">Billing System</p>
            <hr/>
            <p><strong>Bill Number:</strong> {bill_data.get('bill_number')}<br/>
               <strong>Customer:</strong> {bill_data.get('customer_email')}<br/>
               <strong>Date:</strong> {bill_data.get('created_at')}</p>

            <table style="width:100%; border-collapse:collapse; margin:15px 0;">
                <thead>
                    <tr style="background:#2c3e50; color:white;">
                        <th style="padding:8px; border:1px solid #ddd;">ID</th>
                        <th style="padding:8px; border:1px solid #ddd;">Product</th>
                        <th style="padding:8px; border:1px solid #ddd;">Unit</th>
                        <th style="padding:8px; border:1px solid #ddd;">Qty</th>
                        <th style="padding:8px; border:1px solid #ddd;">Purchase</th>
                        <th style="padding:8px; border:1px solid #ddd;">Tax %</th>
                        <th style="padding:8px; border:1px solid #ddd;">Tax</th>
                        <th style="padding:8px; border:1px solid #ddd;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {items_rows}
                </tbody>
            </table>

            <div style="background:#f8f9fa; padding:15px; border-radius:6px;">
                <p style="margin:4px 0;"><strong>Total without tax:</strong> {bill_data.get('total_without_tax'):.2f}</p>
                <p style="margin:4px 0;"><strong>Total tax payable:</strong> {bill_data.get('total_tax_payable'):.2f}</p>
                <p style="margin:4px 0;"><strong>Net price:</strong> {bill_data.get('net_price'):.2f}</p>
                <p style="margin:4px 0;"><strong>Rounded down:</strong> {bill_data.get('rounded_down_net_price'):.2f}</p>
                <p style="margin:4px 0;"><strong>Cash paid:</strong> {bill_data.get('cash_paid'):.2f}</p>
                <p style="margin:4px 0; font-size:1.1em; color:#27ae60;"><strong>Balance payable:</strong> {bill_data.get('balance_payable'):.2f}</p>
                <p style="margin:4px 0;"><strong>Denominations returned:</strong> {denom_str}</p>
            </div>
            <p style="text-align:center; margin-top:20px; color:#777;">Thank you for shopping with us!</p>
        </div>
    </body>
    </html>
    """
    return html


async def send_invoice_email(customer_email: str, bill_data: Dict):
    """
    Async background task to send invoice email.
    Falls back to console log if SMTP not configured.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@billing.local")

    subject = f"Invoice {bill_data.get('bill_number')} - Billing System"

    text_body = _format_invoice_text(bill_data)
    html_body = _format_invoice_html(bill_data)

    # Fallback: log to console with ASCII border if no SMTP config
    if not smtp_host or not smtp_user or not smtp_pass:
        border = "=" * 70
        print("\n" + border)
        print("  [DEV MODE] Invoice Email Fallback - SMTP not configured")
        print(f"  To: {customer_email}")
        print(f"  Subject: {subject}")
        print(border)
        print(text_body)
        print(border + "\n")
        # Also log HTML snippet
        logger.info(f"[Email Fallback] Invoice for {customer_email}: {bill_data.get('bill_number')}")
        return

    # SMTP send
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = customer_email

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        port = int(smtp_port) if smtp_port else 587

        # Use SMTP with TLS
        with smtplib.SMTP(smtp_host, port, timeout=10) as server:
            server.ehlo()
            # Try STARTTLS if port is 587
            if port == 587:
                server.starttls()
                server.ehlo()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, customer_email, msg.as_string())

        print(f"[Email] Invoice {bill_data.get('bill_number')} sent to {customer_email}")
        logger.info(f"Invoice email sent to {customer_email}")

    except Exception as e:
        # Never crash background task - log and fallback to console
        print(f"[Email ERROR] Failed to send invoice to {customer_email}: {e}")
        logger.error(f"Email send failed: {e}")
        # Still log invoice to console so nothing is lost
        print(_format_invoice_text(bill_data))
