
import os
import json
import base64
import urllib.request
import urllib.error

from celery import shared_task
from django.conf import settings

from .models import Payment
from .ticket_utils import generate_ticket_pdf


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_payment_ticket_email(self, payment_id):
    """Generate and email one combined PDF per successful payment."""

    payment = Payment.objects.select_related(
        "user",
        "booking__show_schedule__movie",
    ).get(
        pk=payment_id,
        payment_status="success",
    )

    bookings = list(
        payment.covered_bookings.select_related(
            "seat",
            "show_schedule__movie",
        ).order_by("id")
    )

    # Backward compatibility for older single-seat payments.
    if not bookings:
        bookings = [payment.booking]

    if not all(booking.status == "booked" for booking in bookings):
        return "Not all bookings are confirmed; email skipped."

    if not payment.user.email:
        raise ValueError(
            f"User {payment.user_id} has no email address configured."
        )

    api_key = os.environ.get("BREVO_API_KEY")
    sender_email = (
        os.environ.get("BREVO_SENDER_EMAIL")
        or settings.DEFAULT_FROM_EMAIL
    )

    if not api_key:
        raise ValueError("BREVO_API_KEY is not configured.")

    if not sender_email:
        raise ValueError("BREVO_SENDER_EMAIL is not configured.")

    pdf_bytes = generate_ticket_pdf(
        bookings[0],
        payment=payment,
    )

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    movie_name = bookings[0].show_schedule.movie.name
    seat_numbers = ", ".join(
        booking.seat.seat_number for booking in bookings
    )

    payload = {
        "sender": {
            "name": "BookMySeat",
            "email": sender_email,
        },
        "to": [
            {
                "email": payment.user.email,
                "name": payment.user.get_username(),
            }
        ],
        "subject": f"Your BookMySeat Ticket - Payment #{payment.pk}",
        "textContent": (
            f"Hello {payment.user.get_username()},\n\n"
            f"Your booking for {movie_name} is confirmed.\n"
            f"Seats: {seat_numbers}\n"
            "Your combined ticket is attached to this email.\n\n"
            "Thank you for booking with BookMySeat!"
        ),
        "attachment": [
            {
                "name": f"BookMySeat_Payment_{payment.pk}.pdf",
                "content": pdf_base64,
            }
        ],
    }

    request = urllib.request.Request(
        url="https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        error_details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Brevo API returned HTTP {error.code}: {error_details}"
        ) from error

    return (
        f"Combined ticket email sent for payment {payment.pk}. "
        f"Brevo response: {result}"
    )
