import json
from django.shortcuts import redirect, render, get_object_or_404
from .models import (
    Movie,
    Theater,
    Seat,
    Booking,
    Review,
    ReviewReport,
    ShowSchedule,
    Payment,
)
from .forms import ReviewForm, ReviewReportForm
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Avg
from django.contrib import messages
from urllib.parse import urlparse, parse_qs
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import razorpay
from django.conf import settings
from decimal import Decimal

razorpay_client = razorpay.Client(
    auth=(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET
    )
)


def movie_list(request):
    search_query = request.GET.get('search', '')

    if search_query:
        movies = Movie.objects.filter(
            name__icontains=search_query
        )
    else:
        movies = Movie.objects.all()

    return render(
        request,
        'movies/movie_list.html',
        {'movies': movies}
    )


def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)

    show_schedules = ShowSchedule.objects.filter(
        movie=movie
    ).select_related(
        'theater',
        'screen'
    ).order_by('show_time')

    theaters = Theater.objects.filter(
        show_schedules__movie=movie
    ).distinct()

    return render(
        request,
        'movies/theater_list.html',
        {
            'movie': movie,
            'show_schedules': show_schedules,
            'theaters': theaters,
        }
    )

@login_required(login_url='/login/')
def book_seats(request, show_id):
    show_schedule = get_object_or_404(
        ShowSchedule.objects.select_related(
            'movie',
            'theater',
            'screen'
        ),
        id=show_id
    )

    seats = Seat.objects.filter(
        screen=show_schedule.screen
    ).order_by('seat_number')

    # Remove expired temporary reservations
    Booking.objects.filter(
        show_schedule=show_schedule,
        status='reserved',
        reserved_until__lte=timezone.now()
    ).delete()

    # Permanently booked seats
    booked_seat_ids = Booking.objects.filter(
        show_schedule=show_schedule,
        status='booked'
    ).values_list(
        'seat_id',
        flat=True
    )

    # Temporarily reserved seats
    reserved_seat_ids = Booking.objects.filter(
        show_schedule=show_schedule,
        status='reserved'
    ).values_list(
        'seat_id',
        flat=True
    )

    # Current user's temporarily reserved seats
    my_reserved_seat_ids = Booking.objects.filter(
        show_schedule=show_schedule,
        user=request.user,
        status='reserved'
    ).values_list(
        'seat_id',
        flat=True
    )

    # Current user's reservation, used for countdown
    my_reserved_booking = Booking.objects.filter(
        show_schedule=show_schedule,
        user=request.user,
        status='reserved'
    ).first()

    if request.method == 'POST':

        selected_seats = request.POST.getlist('seats')

        if not selected_seats:
            return render(
                request,
                'movies/seat_selection.html',
                {
                    'show_schedule': show_schedule,
                    'movie': show_schedule.movie,
                    'theater': show_schedule.theater,
                    'screen': show_schedule.screen,
                    'seats': seats,
                    'booked_seat_ids': booked_seat_ids,
                    'reserved_seat_ids': reserved_seat_ids,
                    'my_reserved_seat_ids': my_reserved_seat_ids,
                    'my_reserved_booking': my_reserved_booking,
                    'error': 'Please select at least one seat.',
                }
            )

        error_seats = []

        try:

            with transaction.atomic():

                # -------------------------------------------------
                # STEP 1: Get all selected seat IDs
                # -------------------------------------------------

                selected_seat_ids = sorted(
                    set(int(seat_id) for seat_id in selected_seats)
                )

                # -------------------------------------------------
                # STEP 2: Lock all selected seats
                # -------------------------------------------------

                locked_seats = list(
                    Seat.objects.select_for_update().filter(
                        id__in=selected_seat_ids,
                        screen=show_schedule.screen
                    )
                )

                # Make sure every submitted seat actually exists
                if len(locked_seats) != len(selected_seat_ids):
                    error_seats.append(
                        'Invalid seat selection'
                    )
                    raise ValueError(
                        'Invalid seat selection'
                    )

                # -------------------------------------------------
                # STEP 3: Release current user's old reservations
                # -------------------------------------------------

                Booking.objects.filter(
                    show_schedule=show_schedule,
                    user=request.user,
                    status='reserved'
                ).delete()

                # -------------------------------------------------
                # STEP 4: Check whether selected seats are available
                # -------------------------------------------------

                unavailable_seat_numbers = []

                for seat in locked_seats:

                    # Permanently booked
                    already_booked = Booking.objects.filter(
                        show_schedule=show_schedule,
                        seat=seat,
                        status='booked'
                    ).exists()

                    # Temporarily reserved by another user
                    already_reserved = Booking.objects.filter(
                        show_schedule=show_schedule,
                        seat=seat,
                        status='reserved'
                    ).exists()

                    if already_booked or already_reserved:
                        unavailable_seat_numbers.append(
                            seat.seat_number
                        )

                # -------------------------------------------------
                # STEP 5: If any seat is unavailable,
                # cancel the whole transaction
                # -------------------------------------------------

                if unavailable_seat_numbers:

                    error_seats = unavailable_seat_numbers

                    raise ValueError(
                        'Some selected seats are unavailable.'
                    )

                # -------------------------------------------------
                # STEP 6: Reserve all selected seats
                # -------------------------------------------------

                reserved_until = (
                    timezone.now() +
                    timedelta(minutes=2)
                )

                for seat in locked_seats:

                    Booking.objects.create(
                        user=request.user,
                        seat=seat,
                        show_schedule=show_schedule,
                        status='reserved',
                        reserved_until=reserved_until
                    )

        except ValueError:

            # Refresh seat status after failed transaction

            booked_seat_ids = Booking.objects.filter(
                show_schedule=show_schedule,
                status='booked'
            ).values_list(
                'seat_id',
                flat=True
            )

            reserved_seat_ids = Booking.objects.filter(
                show_schedule=show_schedule,
                status='reserved'
            ).values_list(
                'seat_id',
                flat=True
            )

            my_reserved_seat_ids = Booking.objects.filter(
                show_schedule=show_schedule,
                user=request.user,
                status='reserved'
            ).values_list(
                'seat_id',
                flat=True
            )

            my_reserved_booking = Booking.objects.filter(
                show_schedule=show_schedule,
                user=request.user,
                status='reserved'
            ).first()

            if error_seats:
                error_message = (
                    'The following seats are unavailable: '
                    + ', '.join(error_seats)
                )
            else:
                error_message = (
                    'Unable to reserve the selected seats.'
                )

            return render(
                request,
                'movies/seat_selection.html',
                {
                    'show_schedule': show_schedule,
                    'movie': show_schedule.movie,
                    'theater': show_schedule.theater,
                    'screen': show_schedule.screen,
                    'seats': seats,
                    'booked_seat_ids': booked_seat_ids,
                    'reserved_seat_ids': reserved_seat_ids,
                    'my_reserved_seat_ids': my_reserved_seat_ids,
                    'my_reserved_booking': my_reserved_booking,
                    'error': error_message,
                }
            )

        except IntegrityError:

            return render(
                request,
                'movies/seat_selection.html',
                {
                    'show_schedule': show_schedule,
                    'movie': show_schedule.movie,
                    'theater': show_schedule.theater,
                    'screen': show_schedule.screen,
                    'seats': seats,
                    'booked_seat_ids': booked_seat_ids,
                    'reserved_seat_ids': reserved_seat_ids,
                    'my_reserved_seat_ids': my_reserved_seat_ids,
                    'my_reserved_booking': my_reserved_booking,
                    'error': (
                        'Some selected seats became unavailable. '
                        'Please select again.'
                    ),
                }
            )

        # Everything succeeded
        return redirect(
            'reservation_summary',
            show_id=show_schedule.id
        )

    return render(
        request,
        'movies/seat_selection.html',
        {
            'show_schedule': show_schedule,
            'movie': show_schedule.movie,
            'theater': show_schedule.theater,
            'screen': show_schedule.screen,
            'seats': seats,
            'booked_seat_ids': booked_seat_ids,
            'reserved_seat_ids': reserved_seat_ids,
            'my_reserved_seat_ids': my_reserved_seat_ids,
            'my_reserved_booking': my_reserved_booking,
        }
    )

@login_required(login_url='/login/')
def reservation_summary(request, show_id):

    show_schedule = get_object_or_404(
        ShowSchedule.objects.select_related(
            'movie',
            'theater',
            'screen'
        ),
        id=show_id
    )

    # Get the current user's active reservations
    reservations = Booking.objects.filter(
        user=request.user,
        show_schedule=show_schedule,
        status='reserved',
        reserved_until__gt=timezone.now()
    ).select_related('seat')

    return render(
        request,
        'movies/reservation_summary.html',
        {
            'show_schedule': show_schedule,
            'movie': show_schedule.movie,
            'theater': show_schedule.theater,
            'reservations': reservations,
        }
    )

@login_required(login_url='/login/')
def payment(request, show_id):

    show_schedule = get_object_or_404(
        ShowSchedule.objects.select_related(
            'movie',
            'theater',
            'screen'
        ),
        id=show_id
    )

    if request.method == 'POST':

        try:

            with transaction.atomic():

                reservations = list(
                    Booking.objects.select_for_update().filter(
                        user=request.user,
                        show_schedule=show_schedule,
                        status='reserved',
                        reserved_until__gt=timezone.now()
                    ).select_related('seat')
                )

                if not reservations:
                    raise ValueError(
                        'Your reservation has expired.'
                    )

                total_amount = (
                    show_schedule.ticket_price *
                    len(reservations)
                )

                amount_in_paise = int(
                    total_amount * Decimal('100')
                )

                order_data = {
                    'amount': amount_in_paise,
                    'currency': 'INR',
                    'receipt': (
                        f'booking_{show_schedule.id}_'
                        f'{request.user.id}'
                    ),
                    'notes': {
                        'show_id': str(show_schedule.id),
                        'user_id': str(request.user.id),
                    }
                }

                razorpay_order = razorpay_client.order.create(
                    data=order_data
                )

                print("RAZORPAY ORDER:", razorpay_order)

                Payment.objects.create(
                    booking=reservations[0],
                    user=request.user,
                    amount=total_amount,
                    payment_status='pending',
                    razorpay_order_id=razorpay_order['id']
                )

        except ValueError:

            messages.error(
                request,
                'Your reservation has expired. Please select your seats again.'
            )

            return redirect(
                'book_seats',
                show_id=show_schedule.id
            )

        return render(
            request,
            'movies/payment.html',
            {
                'show_schedule': show_schedule,
                'movie': show_schedule.movie,
                'theater': show_schedule.theater,
                'reservations': reservations,
                'total_amount': total_amount,
                'razorpay_order_id': razorpay_order['id'],
                'razorpay_key_id': settings.RAZORPAY_KEY_ID,
                'amount_in_paise': amount_in_paise,
            }
        )

    reservations = Booking.objects.filter(
        user=request.user,
        show_schedule=show_schedule,
        status='reserved',
        reserved_until__gt=timezone.now()
    ).select_related('seat')

    if not reservations.exists():

        messages.error(
            request,
            'Your seat reservation has expired. Please select your seats again.'
        )

        return redirect(
            'book_seats',
            show_id=show_schedule.id
        )

    total_amount = (
        show_schedule.ticket_price *
        reservations.count()
    )

    return render(
        request,
        'movies/payment.html',
        {
            'show_schedule': show_schedule,
            'movie': show_schedule.movie,
            'theater': show_schedule.theater,
            'reservations': reservations,
            'total_amount': total_amount,
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        }
    )

@login_required(login_url='/login/')
def retry_payment(request, payment_id):

    old_payment = get_object_or_404(
        Payment,
        id=payment_id,
        user=request.user,
        payment_status='cancelled'
    )

    booking = old_payment.booking

    # Make sure the booking is still reserved
    if (
        booking.status != 'reserved'
        or not booking.reserved_until
        or booking.reserved_until <= timezone.now()
    ):
        messages.error(
            request,
            'Your seat reservation has expired. Please select your seats again.'
        )

        return redirect(
            'book_seats',
            show_id=booking.show_schedule.id
        )

    reservations = Booking.objects.filter(
        user=request.user,
        show_schedule=booking.show_schedule,
        status='reserved',
        reserved_until__gt=timezone.now()
    ).select_related('seat')

    total_amount = (
        booking.show_schedule.ticket_price *
        reservations.count()
    )

    amount_in_paise = int(
        total_amount * Decimal('100')
    )

    order_data = {
        'amount': amount_in_paise,
        'currency': 'INR',
        'receipt': (
            f'retry_{booking.id}_{request.user.id}'
        ),
        'notes': {
            'show_id': str(booking.show_schedule.id),
            'user_id': str(request.user.id),
        }
    }

    razorpay_order = razorpay_client.order.create(
        data=order_data
    )

    Payment.objects.create(
        booking=booking,
        user=request.user,
        amount=total_amount,
        payment_status='pending',
        razorpay_order_id=razorpay_order['id']
    )

    return render(
        request,
        'movies/payment.html',
        {
            'show_schedule': booking.show_schedule,
            'movie': booking.show_schedule.movie,
            'theater': booking.show_schedule.theater,
            'reservations': reservations,
            'total_amount': total_amount,
            'razorpay_order_id': razorpay_order['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'amount_in_paise': amount_in_paise,
        }
    )

def get_youtube_embed_url(url):
    if not url:
        return None

    parsed_url = urlparse(url)

    if parsed_url.hostname in ['www.youtube.com', 'youtube.com']:
        video_id = parse_qs(
            parsed_url.query
        ).get('v')

        if video_id:
            return (
                'https://www.youtube-nocookie.com/embed/'
                + video_id[0]
            )

    if parsed_url.hostname in ['youtu.be', 'www.youtu.be']:
        video_id = parsed_url.path.strip('/')

        if video_id:
            return (
                'https://www.youtube-nocookie.com/embed/'
                + video_id
            )

    return None


def movie_detail(request, movie_id):
    movie = get_object_or_404(
        Movie,
        id=movie_id
    )

    reviews = Review.objects.filter(
        movie=movie
    )

    average_rating = reviews.aggregate(
        average=Avg('rating')
    )['average']

    user_has_reviewed = False

    if request.user.is_authenticated:
        user_has_reviewed = Review.objects.filter(
            movie=movie,
            user=request.user
        ).exists()

    youtube_embed_url = get_youtube_embed_url(
        movie.trailer_url
    )

    similar_movies = Movie.objects.filter(
        genres__in=movie.genres.all()
    ).exclude(
        id=movie.id
    ).filter(
        languages__in=movie.languages.all()
    ).distinct()

    return render(
        request,
        'movies/movie_detail.html',
        {
            'movie': movie,
            'reviews': reviews,
            'average_rating': average_rating,
            'user_has_reviewed': user_has_reviewed,
            'youtube_embed_url': youtube_embed_url,
            'similar_movies': similar_movies,
        }
    )


@login_required(login_url='/login/')
def add_review(request, movie_id):
    movie = get_object_or_404(
        Movie,
        id=movie_id
    )

    booking = Booking.objects.filter(
        user=request.user,
        movie=movie
    ).first()

    if not booking:
        messages.error(
            request,
            'You must book this movie before reviewing it.'
        )

        return redirect(
            'movie_detail',
            movie_id=movie.id
        )

    existing_review = Review.objects.filter(
        user=request.user,
        movie=movie
    ).first()

    if existing_review:
        messages.info(
            request,
            'You have already reviewed this movie.'
        )

        return redirect(
            'movie_detail',
            movie_id=movie.id
        )

    if request.method == 'POST':
        form = ReviewForm(request.POST)

        if form.is_valid():
            review = form.save(commit=False)

            review.user = request.user
            review.movie = movie
            review.is_verified_viewer = True

            review.save()

            messages.success(
                request,
                'Your review has been submitted successfully!'
            )

            return redirect(
                'movie_detail',
                movie_id=movie.id
            )

    else:
        form = ReviewForm()

    return render(
        request,
        'movies/add_review.html',
        {
            'form': form,
            'movie': movie,
        }
    )


@login_required(login_url='/login/')
def edit_review(request, review_id):
    review = get_object_or_404(
        Review,
        id=review_id,
        user=request.user
    )

    if request.method == 'POST':
        form = ReviewForm(
            request.POST,
            instance=review
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                'Your review has been updated successfully!'
            )

            return redirect(
                'movie_detail',
                movie_id=review.movie.id
            )

    else:
        form = ReviewForm(
            instance=review
        )

    return render(
        request,
        'movies/edit_review.html',
        {
            'form': form,
            'review': review,
            'movie': review.movie,
        }
    )


@login_required(login_url='/login/')
def report_review(request, review_id):
    review = get_object_or_404(
        Review,
        id=review_id
    )

    if review.user == request.user:
        messages.error(
            request,
            'You cannot report your own review.'
        )

        return redirect(
            'movie_detail',
            movie_id=review.movie.id
        )

    existing_report = ReviewReport.objects.filter(
        review=review,
        reported_by=request.user
    ).exists()

    if existing_report:
        messages.info(
            request,
            'You have already reported this review.'
        )

        return redirect(
            'movie_detail',
            movie_id=review.movie.id
        )

    if request.method == 'POST':
        form = ReviewReportForm(request.POST)

        if form.is_valid():
            report = form.save(commit=False)

            report.review = review
            report.reported_by = request.user

            report.save()

            messages.success(
                request,
                'The review has been reported.'
            )

            return redirect(
                'movie_detail',
                movie_id=review.movie.id
            )

    else:
        form = ReviewReportForm()

    return render(
        request,
        'movies/report_review.html',
        {
            'form': form,
            'review': review,
            'movie': review.movie,
        }
    )


def seat_availability(request, show_id):

    show_schedule = get_object_or_404(
        ShowSchedule,
        id=show_id
    )

    # Remove expired temporary reservations
    Booking.objects.filter(
        show_schedule=show_schedule,
        status='reserved',
        reserved_until__lte=timezone.now()
    ).delete()

    booked_seats = list(
        Booking.objects.filter(
            show_schedule=show_schedule,
            status='booked'
        ).values_list(
            'seat_id',
            flat=True
        )
    )

    reserved_seats = list(
        Booking.objects.filter(
            show_schedule=show_schedule,
            status='reserved'
        ).values_list(
            'seat_id',
            flat=True
        )
    )

    return JsonResponse({
        'booked_seats': booked_seats,
        'reserved_seats': reserved_seats,
    })

@csrf_exempt
@login_required(login_url='/login/')
def verify_payment(request, show_id):

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        }, status=405)

    try:
        data = json.loads(request.body)

        razorpay_payment_id = data.get(
            'razorpay_payment_id'
        )

        razorpay_order_id = data.get(
            'razorpay_order_id'
        )

        razorpay_signature = data.get(
            'razorpay_signature'
        )

        payment = get_object_or_404(
            Payment,
            razorpay_order_id=razorpay_order_id,
            user=request.user
        )
        if payment.payment_status == 'success':
            return JsonResponse({
                'success': True,
                'message': 'Payment already verified.',
                'redirect_url': '/'
            })

        razorpay_client.utility.verify_payment_signature({
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_order_id': razorpay_order_id,
            'razorpay_signature': razorpay_signature,
        })
        existing_payment = Payment.objects.filter(
            razorpay_payment_id=razorpay_payment_id,
            payment_status='success'
        ).exclude(
            id=payment.id
        ).first()

        if existing_payment:
            return JsonResponse({
                'success': True,
                'message': 'Payment already processed.',
                'redirect_url': '/'
            })
        razorpay_payment = razorpay_client.payment.fetch(
            razorpay_payment_id
        )

        if razorpay_payment['status'] != 'captured':
            payment.payment_status = 'failed'
            payment.razorpay_payment_id = razorpay_payment_id
            payment.razorpay_signature = razorpay_signature
            payment.save()

            return JsonResponse({
                'success': False,
                'message': 'Payment was not captured.'
            }, status=400)

        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.payment_status = 'success'
        payment.save()

        reservations = Booking.objects.filter(
            user=request.user,
            show_schedule_id=show_id,
            status='reserved',
            reserved_until__gt=timezone.now()
        )

        reservations.update(
            status='booked',
            reserved_until=None
        )

        return JsonResponse({
            'success': True,
            'message': 'Payment successful.',
            'redirect_url': '/'
        })

    except Exception as e:

        print("Payment verification error:", e)

        return JsonResponse({
            'success': False,
            'message': 'Payment verification failed.'
        }, status=400)
@csrf_exempt
def razorpay_webhook(request):

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        }, status=405)

    try:
        webhook_signature = request.headers.get(
            'X-Razorpay-Signature'
        )

        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

        razorpay_client.utility.verify_webhook_signature(
            request.body.decode('utf-8'),
            webhook_signature,
            webhook_secret
        )

        data = json.loads(request.body)
        event = data.get('event')

        print("RAZORPAY WEBHOOK EVENT:", event)

        # ---------------- PAYMENT CAPTURED ----------------
        if event == 'payment.captured':

            payment_entity = data['payload']['payment']['entity']

            razorpay_payment_id = payment_entity['id']
            razorpay_order_id = payment_entity['order_id']

            payment = Payment.objects.filter(
                razorpay_order_id=razorpay_order_id
            ).first()

            if payment:

                # Prevent duplicate processing
                if payment.payment_status == 'success':
                    return JsonResponse({
                        'success': True,
                        'message': 'Payment already processed.'
                    })

                with transaction.atomic():

                    payment.payment_status = 'success'
                    payment.razorpay_payment_id = razorpay_payment_id
                    payment.save()

                    Booking.objects.filter(
                        user=payment.user,
                        show_schedule=payment.booking.show_schedule,
                        status='reserved'
                    ).update(
                        status='booked',
                        reserved_until=None
                    )

                print("Payment marked as successful.")
                print("Bookings confirmed.")

        # ---------------- PAYMENT FAILED ----------------
        elif event == 'payment.failed':

            payment_entity = data['payload']['payment']['entity']

            razorpay_payment_id = payment_entity['id']
            razorpay_order_id = payment_entity.get('order_id')

            payment = Payment.objects.filter(
                razorpay_order_id=razorpay_order_id
            ).first()

            if payment:

                with transaction.atomic():

                    payment.payment_status = 'failed'
                    payment.razorpay_payment_id = razorpay_payment_id
                    payment.save()

                    Booking.objects.filter(
                        user=payment.user,
                        show_schedule=payment.booking.show_schedule,
                        status='reserved'
                    ).delete()

                print("Payment marked as failed.")
                print("Reserved seats released.")

        # ---------------- ORDER PAID ----------------
        elif event == 'order.paid':

            print("Order paid webhook received.")

        return JsonResponse({
            'success': True,
            'message': 'Webhook processed successfully.'
        })

    except Exception as e:

        print("Webhook verification error:", e)

        return JsonResponse({
            'success': False,
            'message': 'Invalid webhook signature.'
        }, status=400)

@login_required(login_url='/login/')
@csrf_exempt
def cancel_payment(request, show_id):

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        }, status=405)

    try:
        data = json.loads(request.body)

        razorpay_order_id = data.get(
            'razorpay_order_id'
        )

        payment = get_object_or_404(
            Payment,
            razorpay_order_id=razorpay_order_id,
            user=request.user
        )

        if payment.payment_status == 'pending':
            payment.payment_status = 'cancelled'
            payment.save()

        return JsonResponse({
            'success': True,
            'message': 'Payment cancelled.'
        })

    except Exception as e:

        print("Payment cancellation error:", e)

        return JsonResponse({
            'success': False,
            'message': 'Unable to cancel payment.'
        }, status=400)

@login_required(login_url='/login/')
def payment_history(request):

    payments = Payment.objects.filter(
        user=request.user
    ).select_related(
        'booking',
        'booking__show_schedule',
        'booking__show_schedule__movie',
        'booking__seat'
    ).order_by('-created_at')

    return render(
        request,
        'movies/payment_history.html',
        {
            'payments': payments
        }
    )