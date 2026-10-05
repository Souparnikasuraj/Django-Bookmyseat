from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta

from movies.models import (
    Theater,
    Screen,
    Seat,
    ShowSchedule,
    Booking,
    Movie,
)


class Command(BaseCommand):
    help = "Test Booking query performance with 100,000 temporary records"

    def handle(self, *args, **kwargs):

        self.stdout.write(
            self.style.WARNING(
                "Starting 100,000 booking performance test..."
            )
        )

        user = User.objects.first()
        movie = Movie.objects.first()
        theater = Theater.objects.first()
        screen = Screen.objects.first()

        if not all([user, movie, theater, screen]):
            self.stdout.write(
                self.style.ERROR(
                    "Required existing data is missing."
                )
            )
            return

        # Create temporary seats
        seats = [
            Seat(
                screen=screen,
                seat_number=f"PT{i}"
            )
            for i in range(1000)
        ]

        Seat.objects.bulk_create(
            seats,
            batch_size=500
        )

        test_seats = list(
            Seat.objects.filter(
                seat_number__startswith="PT"
            )
        )

        self.stdout.write(
            f"Created {len(test_seats)} temporary seats."
        )

        # Create temporary show schedules
        base_time = timezone.now() - timedelta(days=3)

        show_schedules = [
            ShowSchedule(
                movie=movie,
                theater=theater,
                screen=screen,
                show_time=base_time + timedelta(minutes=i)
            )
            for i in range(100)
        ]

        ShowSchedule.objects.bulk_create(
            show_schedules,
            batch_size=100
        )

        # Get only the shows created for this test
        test_shows = list(
            ShowSchedule.objects.filter(
                movie=movie,
                theater=theater,
                screen=screen,
                show_time__gte=base_time,
                show_time__lt=base_time + timedelta(minutes=100)
            )
        )

        self.stdout.write(
            f"Created {len(test_shows)} temporary shows."
        )

        # Create exactly 100,000 unique bookings
        bookings = []

        for show in test_shows:
            for seat in test_seats:
                bookings.append(
                    Booking(
                        user=user,
                        seat=seat,
                        show_schedule=show,
                        status="booked"
                    )
                )

        self.stdout.write(
            f"Preparing {len(bookings)} bookings..."
        )

        Booking.objects.bulk_create(
            bookings,
            batch_size=5000
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {len(bookings)} temporary bookings."
            )
        )

        # Performance test
        start_time = timezone.now()

        result = (
            Booking.objects
            .filter(
                booked_at__gte=base_time,
                booked_at__lt=timezone.now()
            )
            .values("status")
            .annotate(
                total=Count("id")
            )
        )

        list(result)

        end_time = timezone.now()

        duration = (
            end_time - start_time
        ).total_seconds()

        self.stdout.write(
            self.style.SUCCESS(
                f"Query execution time for 100,000+ bookings: "
                f"{duration:.4f} seconds"
            )
        )

        # Get only test booking IDs
        test_booking_ids = list(
            Booking.objects.filter(
                seat__seat_number__startswith="PT"
            ).values_list("id", flat=True)
        )

        test_show_ids = [
            show.id
            for show in test_shows
        ]

        test_seat_ids = [
            seat.id
            for seat in test_seats
        ]

        # Cleanup only test records
        self.stdout.write(
            "Removing temporary test data..."
        )

        Booking.objects.filter(
            id__in=test_booking_ids
        ).delete()

        ShowSchedule.objects.filter(
            id__in=test_show_ids
        ).delete()

        Seat.objects.filter(
            id__in=test_seat_ids
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Temporary performance-test data removed."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Performance test completed successfully."
            )
        )