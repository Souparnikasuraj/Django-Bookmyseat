
import os
import json
import base64
import urllib.request
import urllib.error

from celery import shared_task
from django.conf import settings

from .models import Booking
from .ticket_utils import generate_ticket_pdf


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_booking_ticket_email(self, booking_id):
    """Generate and email a confirmed booking's PDF ticket using Brevo."""

    booking = Booking.objects.select_related(
        "user",
        "seat",
        "show_schedule__movie",
        "show_schedule__theater",
        "show_schedule__screen",
    ).get(pk=booking_id)

    if booking.status != "booked":
        return "Booking is not confirmed; ticket email skipped."

    if not booking.user.email:
        raise ValueError(
            f"User {booking.user_id} has no email address configured."
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

    pdf_bytes = generate_ticket_pdf(booking)

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    payload = {
        "sender": {
            "name": "BookMySeat",
            "email": sender_email,
        },
        "to": [
            {
                "email": booking.user.email,
                "name": booking.user.get_username(),
            }
        ],
        "subject": f"Your BookMySeat Ticket - Booking #{booking.pk}",
        "textContent": (
            f"Hello {booking.user.get_username()},\n\n"
            f"Your booking for {booking.show_schedule.movie.name} "
            "is confirmed.\n"
            "Your ticket is attached to this email.\n\n"
            "Thank you for booking with BookMySeat!"
        ),
        "attachment": [
            {
                "name": f"BookMySeat_Ticket_{booking.pk}.pdf",
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
        f"Ticket email sent for booking {booking.pk}. "
        f"Brevo response: {result}"
    )
