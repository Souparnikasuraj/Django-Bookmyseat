
from io import BytesIO
from urllib.parse import urlencode

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from .models import Payment
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone


def generate_ticket_pdf(booking):
    """Generate a PDF ticket for one confirmed booking."""

    payment = Payment.objects.filter(
        user=booking.user,
        booking__show_schedule=booking.show_schedule,
        payment_status="success",
    ).order_by("-created_at").first()
    if booking.status != "booked" or payment is None:
        raise ValueError("A confirmed booking with successful payment is required.")

    show = booking.show_schedule
    movie = show.movie
    theater = show.theater
    screen = show.screen

    ticket_token = signing.dumps(
        {
            "booking_id": booking.pk,
            "payment_id": payment.pk,
        },
        salt="bookmyseat.ticket",
    )

    verification_path = reverse(
        "verify_ticket",
        kwargs={"token": ticket_token},
    )
    verification_url = (
        settings.SITE_URL.rstrip("/") + verification_path
        if hasattr(settings, "SITE_URL")
        else verification_path
    )

    qr_image = qrcode.make(verification_url)
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    pdf_buffer = BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"BookMySeat Ticket - Booking {booking.pk}",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TicketHeading",
            parent=styles["Title"],
            textColor=colors.HexColor("#172554"),
            fontSize=22,
            spaceAfter=8,
        )
    )

    story = [
        Paragraph("BookMySeat", styles["TicketHeading"]),
        Paragraph("MOVIE ADMISSION TICKET", styles["Heading2"]),
        Spacer(1, 8 * mm),
    ]

    details = [
        ["Booking ID", str(booking.pk)],
        ["Movie", movie.name],
        ["Theater", theater.name],
        ["Location", theater.location],
        ["Screen", screen.name],
        ["Show date", timezone.localtime(show.show_time).strftime("%d %b %Y")],
        ["Show time", timezone.localtime(show.show_time).strftime("%I:%M %p")],
        ["Seat", booking.seat.seat_number],
        ["Amount paid", f"INR {payment.amount}"],
        ["Payment reference", payment.razorpay_payment_id or payment.razorpay_order_id],
        ["Booking status", "CONFIRMED"],
    ]

    table = Table(
        details,
        colWidths=[48 * mm, 105 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFF6FF")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1E3A8A")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.extend(
        [
            table,
            Spacer(1, 8 * mm),
            Paragraph("Scan the QR code for ticket verification.", styles["Normal"]),
            Spacer(1, 3 * mm),
            Image(qr_buffer, width=35 * mm, height=35 * mm),
            Spacer(1, 5 * mm),
            Paragraph(
                "Please retain this ticket for admission. Each PDF represents one booked seat.",
                styles["Normal"],
            ),
        ]
    )

    document.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()
