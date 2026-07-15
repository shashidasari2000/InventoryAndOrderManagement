"""Invoice PDF generation service."""
from fpdf import FPDF
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.order import BuyerOrder, OrderItem
from app.models.inventory import Product
from typing import Optional
import os
from sqlalchemy.orm import joinedload


class InvoicePDF(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(10, 10, 10)
        self.add_page()

    def header_section(self, user: User, order: BuyerOrder):
        # Title
        title = "Tax Invoice" if (user.gst_number and user.show_gst_on_invoice) else "Invoice"
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, title, ln=True, align="C")
        self.ln(2)

        # Seller details box with border
        y_start = self.get_y()
        self.set_fill_color(245, 245, 245)
        self.rect(10, y_start, 190, 25, "FD")
        
        # Seller details
        self.set_xy(12, y_start + 2)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 5, user.business_name or "Your Business", ln=True)
        self.set_font("Helvetica", "", 8)
        
        detail_parts = []
        if user.business_address:
            detail_parts.append(user.business_address[:60])
        if user.business_phone:
            detail_parts.append(f"Phone: {user.business_phone}")
        if user.gst_number and user.show_gst_on_invoice:
            detail_parts.append(f"GSTIN: {user.gst_number}")
        if user.business_email:
            detail_parts.append(f"Email: {user.business_email}")
        
        detail_text = " | ".join(detail_parts) if detail_parts else ""
        if detail_text:
            self.set_xy(12, y_start + 8)
            self.multi_cell(186, 4, detail_text)
        
        self.set_xy(10, y_start + 25)

    def billing_section(self, order: BuyerOrder, invoice_no: str):
        y = self.get_y()
        
        # Bill To box (left) - with border
        self.set_fill_color(245, 245, 245)
        self.rect(10, y, 95, 30, "FD")
        self.set_xy(12, y + 2)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 4, "Bill To:", ln=True)
        self.set_font("Helvetica", "", 8)
        self.set_xy(12, y + 7)
        self.cell(0, 4, order.buyer_name or "Cash Customer", ln=True)
        if order.buyer_phone:
            self.set_xy(12, y + 12)
            self.cell(0, 4, f"Contact No: {order.buyer_phone}", ln=True)

        # Invoice Details box (right) - with border
        self.rect(107, y, 93, 30, "FD")
        self.set_xy(109, y + 2)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 4, "Invoice Details:", ln=True)
        self.set_font("Helvetica", "", 8)
        self.set_xy(109, y + 7)
        self.cell(0, 4, f"No: {invoice_no}", ln=True)
        self.set_xy(109, y + 12)
        invoice_date = order.checked_out_at or order.created_at
        self.cell(0, 4, f"Date: {invoice_date.strftime('%d-%m-%Y')}", ln=True)
        self.set_xy(109, y + 17)
        due_date = invoice_date + timedelta(days=15)
        self.cell(0, 4, f"Due Date: {due_date.strftime('%d-%m-%Y')}", ln=True)

        self.set_xy(10, y + 32)

    def items_table(self, order: BuyerOrder, db: Session):
        # Table header
        self.set_fill_color(245, 245, 245)
        self.set_font("Helvetica", "B", 9)
        
        headers = ["#", "Item Name", "HSN/SAC", "Quantity", "Unit", "Price/Unit", "Amount"]
        widths = [10, 55, 25, 20, 20, 30, 30]
        aligns = ["C", "L", "C", "R", "C", "R", "R"]
        
        y = self.get_y()
        for i, (header, width) in enumerate(zip(headers, widths)):
            self.cell(width, 8, header, border=1, fill=True, align=aligns[i])
        self.ln(8)

        # Table rows
        self.set_font("Helvetica", "", 9)
        total_qty = 0
        
        for idx, item in enumerate(order.items, 1):
            product = db.query(Product).filter(Product.id == item.product_id).first()
            name = product.name if product else "Unknown"
            qty = float(item.entered_quantity if item.entered_quantity is not None else item.quantity)
            unit_label = item.unit or (product.unit if product else "pcs")
            price = float(item.unit_price)
            amount = float(item.total_price)
            total_qty += qty

            row_data = [
                (str(idx), "C"),
                (name[:30], "L"),  # Truncate long names
                ("", "C"),  # HSN/SAC empty for now
                (f"{qty:g}", "R"),
                (unit_label, "C"),
                (f"Rs. {price:,.2f}", "R"),
                (f"Rs. {amount:,.2f}", "R"),
            ]
            
            for i, (text, align) in enumerate(row_data):
                self.cell(widths[i], 8, text, border=1, align=align)
            self.ln(8)

        # Total row
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(245, 245, 245)
        self.cell(90, 8, "Total", border=1, fill=True, align="R")
        self.cell(20, 8, f"{total_qty:g}", border=1, fill=True, align="R")
        self.cell(20, 8, "", border=1, fill=True)
        self.cell(30, 8, "", border=1, fill=True)
        self.cell(30, 8, f"Rs. {float(order.total_amount):,.2f}", border=1, fill=True, align="R")
        self.ln(8)

    def totals_section(self, order: BuyerOrder):
        y = self.get_y()
        
        # Right-aligned totals box with border - smaller height
        self.set_xy(120, y)
        self.set_fill_color(245, 245, 245)
        self.rect(120, y, 80, 42, "FD")
        
        self.set_xy(122, y + 3)
        self.set_font("Helvetica", "", 9)
        self.cell(40, 5, "Sub Total", align="L")
        self.cell(35, 5, f": Rs. {float(order.subtotal):,.2f}", align="R")
        
        self.set_xy(122, y + 10)
        self.cell(40, 5, "Discount", align="L")
        self.cell(35, 5, f": Rs. {float(order.discount):,.2f}", align="R")
        
        self.set_xy(122, y + 17)
        self.set_font("Helvetica", "B", 10)
        self.cell(40, 6, "Total", align="L")
        self.cell(35, 6, f": Rs. {float(order.total_amount):,.2f}", align="R")
        
        # Amount in words - inside the box
        self.set_xy(122, y + 26)
        self.set_font("Helvetica", "B", 8)
        self.cell(75, 4, "Invoice Amount In Words:", ln=False)
        self.set_xy(122, y + 31)
        self.set_font("Helvetica", "", 8)
        words = self._number_to_words(int(order.total_amount))
        self.cell(75, 4, f"{words} only", ln=False)

        # Position for footer - right after the box
        self.set_xy(10, y + 44)

    def footer_section(self, user: User):
        y = self.get_y()
        
        # Terms and Conditions - full width box (10 to 200)
        self.set_fill_color(245, 245, 245)
        self.rect(10, y, 190, 14, "FD")
        self.set_xy(12, y + 2)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 4, "Terms And Conditions:", ln=True)
        self.set_font("Helvetica", "", 8)
        self.set_xy(12, y + 7)
        self.cell(0, 4, "Thank you for doing business with us.", ln=False)
        
        # Signature section - below terms box, right-aligned
        sig_section_y = y + 18
        sig_x = 150  # common x for all signature elements
        sig_w = 50   # width for text and image

        self.set_xy(sig_x, sig_section_y)
        self.set_font("Helvetica", "", 8)
        self.cell(sig_w, 4, f"For {user.business_name or 'Your Business'}:", align="L", ln=False)
        
        # Signature image or line
        sig_y = sig_section_y + 6
        if user.signature_image:
            try:
                import base64
                from io import BytesIO
                img_data = base64.b64decode(user.signature_image.split(',')[-1])
                img = BytesIO(img_data)
                self.image(img, x=sig_x, y=sig_y, w=sig_w, h=18)
                sig_y += 20
            except Exception:
                self.line(sig_x, sig_y + 8, sig_x + sig_w, sig_y + 8)
                sig_y += 10
        else:
            self.line(sig_x, sig_y + 8, sig_x + sig_w, sig_y + 8)
            sig_y += 10
        
        self.set_xy(sig_x, sig_y + 2)
        self.cell(sig_w, 4, "Authorized Signatory", align="L", ln=False)

    def _number_to_words(self, number: int) -> str:
        """Convert number to words (simplified for Indian format)."""
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
        teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", 
                 "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        
        if number == 0:
            return "Zero"
        
        def convert_less_than_thousand(n):
            if n == 0:
                return ""
            elif n < 10:
                return units[n]
            elif n < 20:
                return teens[n - 10]
            elif n < 100:
                return tens[n // 10] + ("" if n % 10 == 0 else " " + units[n % 10])
            else:
                return units[n // 100] + " Hundred" + ("" if n % 100 == 0 else " and " + convert_less_than_thousand(n % 100))
        
        def convert(n):
            if n == 0:
                return "Zero"
            
            result = ""
            
            # Crores
            crores = n // 10000000
            if crores > 0:
                result += convert_less_than_thousand(crores) + " Crore "
                n %= 10000000
            
            # Lakhs
            lakhs = n // 100000
            if lakhs > 0:
                result += convert_less_than_thousand(lakhs) + " Lakh "
                n %= 100000
            
            # Thousands
            thousands = n // 1000
            if thousands > 0:
                result += convert_less_than_thousand(thousands) + " Thousand "
                n %= 1000
            
            # Remaining
            if n > 0:
                result += convert_less_than_thousand(n)
            
            return result.strip()
        
        return convert(number)


def _generate_invoice_number(user: User) -> str:
    prefix = user.invoice_prefix or "INV"
    next_num = user.invoice_next_number or "1"
    return f"{prefix}-{int(next_num):04d}"


def _load_invoice(db: Session, order_id: UUID, user_id: UUID):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    order = db.query(BuyerOrder).options(
        joinedload(BuyerOrder.items)
    ).filter(
        BuyerOrder.id == order_id,
        BuyerOrder.user_id == user_id
    ).first()
    if not order:
        raise ValueError("Order not found")
    return user, order


def get_invoice_data(db: Session, order_id: UUID, user_id: UUID) -> dict:
    """Return invoice data for preview, print, and WhatsApp sharing."""
    user, order = _load_invoice(db, order_id, user_id)
    invoice_no = _generate_invoice_number(user)

    items = []
    for idx, item in enumerate(order.items, 1):
        product = db.query(Product).filter(Product.id == item.product_id).first()
        base_unit_label = (product.base_unit or product.unit) if product else "pcs"
        items.append({
            "sno": idx,
            "name": product.name if product else "Unknown",
            "unit": item.unit or base_unit_label,
            "quantity": float(item.entered_quantity if item.entered_quantity is not None else item.quantity),
            "base_unit": base_unit_label,
            "base_quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "total_price": float(item.total_price),
        })

    invoice_date = order.checked_out_at or order.created_at
    return {
        "invoice_number": invoice_no,
        "invoice_date": invoice_date.isoformat(),
        "due_date": (invoice_date + timedelta(days=15)).isoformat(),
        "business_name": user.business_name or "Your Business",
        "business_address": user.business_address,
        "business_phone": user.business_phone,
        "business_email": user.business_email,
        "business_gst": user.gst_number if user.show_gst_on_invoice else None,
        "signature_image": user.signature_image,
        "buyer_name": order.buyer_name or "Cash Customer",
        "buyer_phone": order.buyer_phone,
        "items": items,
        "subtotal": float(order.subtotal),
        "discount": float(order.discount),
        "total_amount": float(order.total_amount),
        "total_quantity": sum(i["quantity"] for i in items),
        "amount_in_words": InvoicePDF()._number_to_words(int(order.total_amount)),
        "is_tax_invoice": bool(user.gst_number and user.show_gst_on_invoice),
    }


def generate_invoice_pdf(db: Session, order_id: UUID, user_id: UUID) -> bytes:
    """Generate invoice PDF for an order."""
    user, order = _load_invoice(db, order_id, user_id)
    invoice_no = _generate_invoice_number(user)
    
    # Increment invoice number
    next_num = user.invoice_next_number or "1"
    user.invoice_next_number = str(int(next_num) + 1)
    db.commit()
    
    # Generate PDF
    pdf = InvoicePDF()
    pdf.header_section(user, order)
    pdf.billing_section(order, invoice_no)
    pdf.items_table(order, db)
    pdf.totals_section(order)
    pdf.footer_section(user)
    
    return pdf.output(dest="S")
