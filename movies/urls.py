from django.urls import path
from . import views

urlpatterns=[
    path('', views.movie_list, name='movie_list'),
    path('<int:movie_id>/theaters/', views.theater_list, name='theater_list'),
    path('show/<int:show_id>/book/', views.book_seats, name='book_seats'),
    path(
        'show/<int:show_id>/availability/',
        views.seat_availability,
        name='seat_availability'
    ),
    path(
        'reservation/<int:show_id>/',
        views.reservation_summary,
        name='reservation_summary'
    ),
    path(
        'payment/<int:show_id>/',
        views.payment,
        name='payment'
    ),
    path('retry-payment/<int:payment_id>/', views.retry_payment, name='retry_payment'),
    path('payment/<int:show_id>/cancel/', views.cancel_payment, name='cancel_payment'),
    path(
        'payment-history/',
        views.payment_history,
        name='payment_history'
    ),
    path(
        'payment/<int:show_id>/verify/',
        views.verify_payment,
        name='verify_payment'
    ),
    path(
        'razorpay/webhook/',
        views.razorpay_webhook,
        name='razorpay_webhook'
    ),

    path(
        '<int:movie_id>/review/add/',
        views.add_review,
        name='add_review'
    ),

    path(
        'review/<int:review_id>/edit/',
        views.edit_review,
        name='edit_review'
    ),

    path(
        'review/<int:review_id>/report/',
        views.report_review,
        name='report_review'
    ),

    path(
        '<int:movie_id>/',
        views.movie_detail,
        name='movie_detail'
    ),
]
