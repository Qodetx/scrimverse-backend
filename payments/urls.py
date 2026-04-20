from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    # Payment APIs
    path("initiate/", views.initiate_payment, name="initiate_payment"),
    path("status/", views.check_payment_status, name="check_payment_status"),
    path("list/", views.list_payments, name="list_payments"),
    path("earnings/", views.player_earnings, name="player_earnings"),
    path("host-transactions/", views.host_transactions, name="host_transactions"),
    # Refund APIs
    path("refund/initiate/", views.initiate_refund, name="initiate_refund"),
    # PhonePe Webhook
    path("callback/", views.phonepe_callback, name="phonepe_callback"),
]
