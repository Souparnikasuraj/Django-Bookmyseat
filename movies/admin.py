from django.contrib import admin

from .models import (
    Movie,
    Screen,
    ShowSchedule,
    Theater,
    Seat,
    Booking,
    Genre,
    Language,
    CastMember,
    MoviePoster,
    Review,
    ReviewReport,
    Payment,
)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(CastMember)
class CastMemberAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class MoviePosterInline(admin.TabularInline):
    model = MoviePoster
    extra = 1

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'rating',
        'certification',
        'duration',
        'release_date',
    )

    search_fields = ('name', 'description')

    list_filter = (
        'certification',
        'release_date',
        'genres',
        'languages',
    )
    inlines = [MoviePosterInline]


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ('name', 'location')
    list_filter = ('location',)

@admin.register(ShowSchedule)
class ShowScheduleAdmin(admin.ModelAdmin):
    list_display = ('movie', 'theater', 'show_time')
    list_filter = ('movie', 'theater')
    search_fields = ('movie__name', 'theater__name')


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ('name', 'theater')
    list_filter = ('theater',)

@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ('screen', 'seat_number')
    list_filter = ('screen',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'seat',
        'show_schedule',
        'booked_at',
    )

    list_filter = (
        'show_schedule',
    )

    search_fields = (
        'user__username',
        'seat__seat_number',
        'show_schedule__movie__name',
        'show_schedule__theater__name',
    )

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'booking',
        'user',
        'amount',
        'payment_status',
        'razorpay_order_id',
        'razorpay_payment_id',
        'created_at',
    )

    list_filter = (
        'payment_status',
        'created_at',
    )

    search_fields = (
        'user__username',
        'razorpay_order_id',
        'razorpay_payment_id',
    )

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('movie', 'user', 'rating', 'created_at', 'updated_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('movie__name', 'user__username', 'comment')

@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = (
        'review',
        'reported_by',
        'reason',
        'created_at',
        'is_resolved',
    )

    list_filter = (
        'is_resolved',
        'created_at',
    )

    search_fields = (
        'review__comment',
        'reported_by__username',
        'reason',
    )