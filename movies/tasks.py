
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Booking
from .ticket_utils import generate_ticket_pdf


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_booking_ticket_email(self, booking_id):
    """Generate and email a confirmed booking's PDF ticket."""

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

    pdf_bytes = generate_ticket_pdf(booking)

    email = EmailMessage(
        subject=f"Your BookMySeat Ticket - Booking #{booking.pk}",
        body=(
            f"Hello {booking.user.get_username()},\n\n"
            f"Your booking for {booking.show_schedule.movie.name} is confirmed.\n"
            "Your ticket is attached to this email.\n\n"
            "Thank you for booking with BookMySeat!"
        ),
        from_email=getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            None,
        ),
        to=[booking.user.email],
    )

    email.attach(
        f"BookMySeat_Ticket_{booking.pk}.pdf",
        pdf_bytes,
        "application/pdf",
    )
    email.send(fail_silently=False)

    return f"Ticket email sent for booking {booking.pk}."
