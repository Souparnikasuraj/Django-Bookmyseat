
from io import BytesIO

import qrcode

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
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
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import Payment


def get_payment_bookings(payment):
    """Return every booking covered by a payment, including legacy payments."""
    bookings = list(
        payment.covered_bookings.select_related(
            'user',
            'seat',
            'show_schedule__movie',
            'show_schedule__theater',
            'show_schedule__screen',
        ).order_by('seat__seat_number')
    )

    if not bookings:
        booking = payment.booking
        booking = (
            type(booking).objects.select_related(
                'user',
                'seat',
                'show_schedule__movie',
                'show_schedule__theater',
                'show_schedule__screen',
            ).get(pk=booking.pk)
        )
        bookings = [booking]

    return bookings


def generate_ticket_pdf(booking, payment=None):
    """Generate one combined PDF for all bookings covered by a payment."""

    if payment is None:
        payment = Payment.objects.filter(
            user=booking.user,
            payment_status='success',
        ).filter(
            Q(covered_bookings=booking) |
            Q(booking=booking)
        ).distinct().order_by('-created_at').first()

    if payment is None:
        raise ValueError(
            "A successful payment associated with this booking is required."
        )

    if (
        payment.user_id != booking.user_id
        or payment.payment_status != 'success'
    ):
        raise ValueError("The payment does not belong to this booking.")

    bookings = get_payment_bookings(payment)

    if not bookings:
        raise ValueError("No bookings were found for this payment.")

    if not any(item.pk == booking.pk for item in bookings):
        raise ValueError("This booking is not associated with the payment.")


    if any(item.status != 'booked' for item in bookings):
        raise ValueError("All bookings must be confirmed before downloading.")

    if any(item.user_id != payment.user_id for item in bookings):
        raise ValueError("The payment contains an invalid booking.")

    # A combined ticket must represent one show.
    show = bookings[0].show_schedule

    if any(item.show_schedule_id != show.pk for item in bookings):
        raise ValueError("Bookings in this payment belong to different shows.")

    movie = show.movie
    theater = show.theater
    screen = show.screen

    ticket_token = signing.dumps(
        {"payment_id": payment.pk},
        salt="bookmyseat.ticket",
    )

    verification_path = reverse(
        "verify_ticket",
        kwargs={"token": ticket_token},
    )

    verification_url = (
        settings.SITE_URL.rstrip("/") + verification_path
        if getattr(settings, "SITE_URL", None)
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
        title=f"BookMySeat Ticket - Payment {payment.pk}",
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

    seat_numbers = ", ".join(
        item.seat.seat_number for item in bookings
    )
    booking_ids = ", ".join(str(item.pk) for item in bookings)

    details = [
        ["Payment ID", str(payment.pk)],
        ["Booking IDs", booking_ids],
        ["Movie", movie.name],
        ["Theater", theater.name],
        ["Location", theater.location],
        ["Screen", screen.name],
        [
            "Show date",
            timezone.localtime(show.show_time).strftime("%d %b %Y"),
        ],
        [
            "Show time",
            timezone.localtime(show.show_time).strftime("%I:%M %p"),
        ],
        ["Seats", seat_numbers],
        ["Number of seats", str(len(bookings))],
        ["Total transaction amount", f"INR {payment.amount}"],
        [
            "Payment reference",
            payment.razorpay_payment_id or payment.razorpay_order_id,
        ],
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

    story = [
        Paragraph("BookMySeat", styles["TicketHeading"]),
        Paragraph("MOVIE ADMISSION TICKET", styles["Heading2"]),
        Spacer(1, 8 * mm),
        table,
        Spacer(1, 8 * mm),
        Paragraph(
            "Scan this QR code to verify this payment and all seats "
            "included in this ticket.",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Image(qr_buffer, width=40 * mm, height=40 * mm),
        Spacer(1, 5 * mm),
        Paragraph(
            "This is one combined ticket for all seats listed above.",
            styles["Normal"],
        ),
    ]

    document.build(story)
    pdf_buffer.seek(0)

    return pdf_buffer.getvalue()
