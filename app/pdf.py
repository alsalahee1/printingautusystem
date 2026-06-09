"""Server-side PDF generation with ReportLab (no system libraries required).

A single `_render` builder lays out the company header, a recipient block, a
line-item table and optional totals/notes — shared by quotations, invoices and
delivery orders so they look consistent. Returns raw PDF bytes for download or
email attachment.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_styles = getSampleStyleSheet()
_small = ParagraphStyle("small", parent=_styles["Normal"], fontSize=8, leading=10)
_normal = ParagraphStyle("n", parent=_styles["Normal"], fontSize=9, leading=12)
_title = ParagraphStyle("t", parent=_styles["Title"], fontSize=20, alignment=2, textColor=colors.HexColor("#6c757d"))
_h = ParagraphStyle("h", parent=_styles["Normal"], fontSize=14, leading=16, spaceAfter=2)


def _render(*, title, doc_meta, party_label, party_lines, settings,
            columns, rows, col_aligns, col_widths, totals=None, footer_lines=None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title=title)
    el = []

    # Header: company (left) + document title/meta (right).
    addr = (settings.company_address or "").replace("\n", "<br/>")
    contact = []
    if settings.company_phone:
        contact.append(f"Tel: {settings.company_phone}")
    if settings.company_email:
        contact.append(settings.company_email)
    left = [Paragraph(settings.company_name or "My Printing Press", _h)]
    if addr:
        left.append(Paragraph(addr, _small))
    if contact:
        left.append(Paragraph(" · ".join(contact), _small))
    meta = "<br/>".join(f"<b>{k}:</b> {v}" for k, v in doc_meta)
    right = [Paragraph(title.upper(), _title), Spacer(1, 4), Paragraph(meta, _small)]
    head = Table([[left, right]], colWidths=[100 * mm, 74 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [head, Spacer(1, 10)]

    el.append(Paragraph(f"<b>{party_label}</b>", _small))
    for line in party_lines:
        if line:
            el.append(Paragraph(line, _normal))
    el.append(Spacer(1, 10))

    # Line-item table.
    data = [columns] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#495057")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#ced4da")),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#e9ecef")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, a in enumerate(col_aligns):
        style.append(("ALIGN", (i, 0), (i, -1), a))
    table.setStyle(TableStyle(style))
    el.append(table)

    if totals:
        el.append(Spacer(1, 6))
        trows = [[k, v] for k, v in totals]
        tt = Table(trows, colWidths=[140 * mm, 34 * mm])
        tstyle = [("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        tstyle.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        tstyle.append(("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor("#ced4da")))
        tt.setStyle(TableStyle(tstyle))
        el.append(tt)

    for line in (footer_lines or []):
        el += [Spacer(1, 10), Paragraph(line, _small)]

    doc.build(el)
    return buf.getvalue()


def _cur(settings, v):
    return f"{settings.currency} {v:,.2f}"


def quotation_pdf(q, settings) -> bytes:
    rows = [[
        str(it.line_no),
        Paragraph(f"<b>{it.title}</b><br/>{it.finished_width_mm:g}×{it.finished_height_mm:g}mm, "
                  f"{it.colors_front}/{it.colors_back}"
                  + (f"<br/>Finishing: {', '.join(f.finishing.name for f in it.finishings)}" if it.finishings else ""),
                  _small),
        f"{it.quantity}", f"{it.unit_price:.3f}", _cur(settings, it.line_total),
    ] for it in q.items]
    return _render(
        title="Quotation",
        doc_meta=[("No", q.number), ("Date", q.date), ("Valid until", q.valid_until or "—")],
        party_label="Prepared for", party_lines=[
            f"<b>{q.customer.name}</b>", q.customer.company,
            (q.customer.address or "").replace("\n", "<br/>"), q.customer.phone],
        settings=settings,
        columns=["#", "Description", "Qty", "Unit", "Amount"],
        rows=rows, col_aligns=["LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"],
        col_widths=[8 * mm, 96 * mm, 18 * mm, 22 * mm, 30 * mm],
        totals=[("Subtotal", _cur(settings, q.subtotal)),
                (f"Tax ({q.tax_pct:g}%)", _cur(settings, q.tax_amount)),
                ("Total", _cur(settings, q.total))],
        footer_lines=[x for x in [q.notes and f"<b>Notes:</b> {q.notes}",
                                  q.terms and q.terms.replace("\n", "<br/>")] if x],
    )


def invoice_pdf(inv, settings) -> bytes:
    rows = [[str(it.line_no), Paragraph(it.description, _small),
             f"{it.quantity:g}", f"{it.unit_price:.2f}", _cur(settings, it.amount)]
            for it in inv.items]
    totals = [("Subtotal", _cur(settings, inv.subtotal)),
              (f"Tax ({inv.tax_pct:g}%)", _cur(settings, inv.tax_amount)),
              ("Total", _cur(settings, inv.total))]
    if inv.paid_amount:
        totals += [("Paid", _cur(settings, inv.paid_amount)),
                   ("Balance Due", _cur(settings, inv.balance))]
    return _render(
        title="Invoice",
        doc_meta=[("No", inv.number), ("Date", inv.date),
                  ("Due", inv.due_date or "—"), ("Status", inv.status)],
        party_label="Bill to", party_lines=[
            f"<b>{inv.customer.name}</b>", inv.customer.company,
            (inv.customer.address or "").replace("\n", "<br/>")],
        settings=settings,
        columns=["#", "Description", "Qty", "Unit Price", "Amount"],
        rows=rows, col_aligns=["LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"],
        col_widths=[8 * mm, 96 * mm, 18 * mm, 22 * mm, 30 * mm],
        totals=totals,
        footer_lines=[x for x in [inv.notes and f"<b>Notes:</b> {inv.notes}",
                                  inv.terms and inv.terms.replace("\n", "<br/>")] if x],
    )


def delivery_order_pdf(do, settings) -> bytes:
    rows = [[str(it.line_no), Paragraph(it.description, _small), f"{it.quantity:g}"]
            for it in do.items]
    meta = [("No", do.number), ("Date", do.date)]
    if do.job:
        meta.append(("Job", do.job.number))
    return _render(
        title="Delivery Order",
        doc_meta=meta,
        party_label="Deliver to", party_lines=[
            f"<b>{do.customer.name}</b>", do.customer.company,
            (do.delivered_to or do.customer.address or "").replace("\n", "<br/>")],
        settings=settings,
        columns=["#", "Description", "Quantity"],
        rows=rows, col_aligns=["LEFT", "LEFT", "RIGHT"],
        col_widths=[10 * mm, 134 * mm, 30 * mm],
        footer_lines=[do.notes and f"<b>Notes:</b> {do.notes}"] if do.notes else None,
    )
