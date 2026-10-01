from django.db import models
from django.contrib.auth.models import User


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class CastMember(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(
        upload_to='cast/',
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name


class Movie(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='movies/')

    # Keep these for now because your existing movies already use them.
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()

    description = models.TextField(blank=True, null=True)

    # New fields for Task 1
    genres = models.ManyToManyField(
        Genre,
        blank=True,
        related_name='movies'
    )

    languages = models.ManyToManyField(
        Language,
        blank=True,
        related_name='movies'
    )

    cast_members = models.ManyToManyField(
        CastMember,
        blank=True,
        related_name='movies'
    )

    certification = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    duration = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Duration in minutes"
    )

    release_date = models.DateField(
        blank=True,
        null=True
    )

    trailer_url = models.URLField(
        blank=True,
        null=True,
        help_text="YouTube trailer URL"
    )
    
    def __str__(self):
        return self.name

class MoviePoster(models.Model):
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name='posters'
    )
    image = models.ImageField(upload_to='movies/posters/')
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.movie.name} Poster"
    
class Theater(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Screen(models.Model):
    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name='screens'
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.theater.name} - {self.name}"


class ShowSchedule(models.Model):
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name='show_schedules'
    )

    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name='show_schedules'
    )

    screen = models.ForeignKey(
        Screen,
        on_delete=models.CASCADE,
        related_name='show_schedules',
    )

    show_time = models.DateTimeField()

    ticket_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=200.00
    )
    
    def __str__(self):
        return f"{self.movie.name} - {self.theater.name} - {self.show_time}"


class Seat(models.Model):
    screen = models.ForeignKey(
        Screen,
        on_delete=models.CASCADE,
        related_name='seats'
    )
    seat_number = models.CharField(max_length=10)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['screen', 'seat_number'],
                name='unique_seat_per_screen'
            )
        ]

    def __str__(self):
        return f"{self.seat_number} - {self.screen}"
class Booking(models.Model):
    STATUS_CHOICES = [
        ('reserved', 'Reserved'),
        ('booked', 'Booked'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    seat = models.ForeignKey(
        Seat,
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    show_schedule = models.ForeignKey(
        ShowSchedule,
        on_delete=models.CASCADE,
        related_name='bookings',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='reserved'
    )

    booked_at = models.DateTimeField(auto_now_add=True)

    reserved_until = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['show_schedule', 'seat'],
                name='unique_seat_per_show'
            )
        ]

    def __str__(self):
        return (
            f"Booking by {self.user.username} "
            f"for {self.seat.seat_number} - "
            f"{self.show_schedule}"
        )

class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )

    razorpay_order_id = models.CharField(
        max_length=255,
        unique=True
    )

    razorpay_payment_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    razorpay_signature = models.CharField(
        max_length=500,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"Payment - {self.user.username} - "
            f"{self.amount} - {self.payment_status}"
        )

class Review(models.Model):
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='movie_reviews'
    )
    rating = models.PositiveIntegerField()
    comment = models.TextField()
    is_verified_viewer = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('movie', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.movie.name} ({self.rating}/5)"

class ReviewReport(models.Model):
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='reports'
    )

    reported_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='review_reports'
    )

    reason = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    is_resolved = models.BooleanField(default=False)

    class Meta:
        unique_together = ('review', 'reported_by')
        ordering = ['-created_at']

    def __str__(self):
        return f"Report by {self.reported_by.username} - {self.review}"