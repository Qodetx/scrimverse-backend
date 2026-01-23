"""
Payment Views for PhonePe Integration
"""

import json
import logging
from uuid import uuid4

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from decouple import config
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import HostProfile, PlayerProfile
from tournaments.models import Tournament, TournamentRegistration

from .models import Payment, Refund
from .serializers import InitiatePaymentSerializer, InitiateRefundSerializer, PaymentSerializer, PaymentStatusSerializer
from .services import phonepe_service

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Initiate a payment transaction

    Request Body:
    {
        "payment_type": "tournament_plan" | "scrim_plan" | "entry_fee",
        "amount": 299.00,
        "tournament_id": 1,  // Required for tournament_plan and scrim_plan
        "registration_id": 1,  // Required for entry_fee
        "redirect_url": "https://yoursite.com/payment/callback"  // Optional
    }
    """
    serializer = InitiatePaymentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    user = request.user

    try:
        # Get user profiles
        player_profile = None
        host_profile = None

        try:
            player_profile = user.player_profile
        except PlayerProfile.DoesNotExist:
            pass

        try:
            host_profile = user.host_profile
        except HostProfile.DoesNotExist:
            pass

        # Get tournament if provided
        tournament = None
        if data.get("tournament_id"):
            try:
                tournament = Tournament.objects.get(id=data["tournament_id"])
            except Tournament.DoesNotExist:
                return Response({"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get registration if provided
        registration = None
        if data.get("registration_id"):
            try:
                registration = TournamentRegistration.objects.get(id=data["registration_id"], player=player_profile)
            except TournamentRegistration.DoesNotExist:
                return Response({"error": "Registration not found"}, status=status.HTTP_404_NOT_FOUND)

        # Generate unique merchant order ID
        merchant_order_id = f"ORD_{uuid4().hex[:16].upper()}"

        # Convert amount to paisa
        amount_paisa = int(data["amount"] * 100)

        # Prepare redirect URL
        frontend_url = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(",")[0]
        redirect_url = data.get("redirect_url") or f"{frontend_url}/payment/callback"

        # Prepare metadata
        meta_info = {
            "udf1": str(user.id),
            "udf2": data["payment_type"],
            "udf3": str(tournament.id) if tournament else "",
            "udf4": str(registration.id) if registration else "",
            "udf5": merchant_order_id,
        }

        # Create payment record
        with transaction.atomic():
            payment = Payment.objects.create(
                merchant_order_id=merchant_order_id,
                payment_type=data["payment_type"],
                amount=data["amount"],
                amount_paisa=amount_paisa,
                user=user,
                player_profile=player_profile,
                host_profile=host_profile,
                tournament=tournament,
                registration=registration,
                status="pending",
                meta_info=meta_info,
            )

            # Initiate payment with PhonePe
            phonepe_response = phonepe_service.initiate_payment(
                amount=amount_paisa,
                redirect_url=redirect_url,
                merchant_order_id=merchant_order_id,
                meta_info_dict=meta_info,
                message=f"Payment for {data['payment_type']}",
                expire_after=3600,  # 1 hour
                disable_payment_retry=False,
            )

            if not phonepe_response.get("success"):
                payment.status = "failed"
                payment.error_code = phonepe_response.get("error_code", "")
                payment.save()

                return Response(
                    {"error": "Failed to initiate payment", "details": phonepe_response.get("error")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Update payment with PhonePe response
            payment.phonepe_order_id = phonepe_response.get("order_id")
            payment.redirect_url = phonepe_response.get("redirect_url")
            payment.save()

            logger.info(f"Payment initiated: {merchant_order_id} for user {user.username}")

            return Response(
                {
                    "success": True,
                    "merchant_order_id": merchant_order_id,
                    "phonepe_order_id": phonepe_response.get("order_id"),
                    "redirect_url": phonepe_response.get("redirect_url"),
                    "state": phonepe_response.get("state"),
                    "expire_at": phonepe_response.get("expire_at"),
                },
                status=status.HTTP_200_OK,
            )

    except Exception as e:
        logger.error(f"Error initiating payment: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_payment_status(request):
    """
    Check payment status

    Request Body:
    {
        "merchant_order_id": "ORD_ABC123"
    }
    """
    serializer = PaymentStatusSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    merchant_order_id = serializer.validated_data["merchant_order_id"]

    try:
        # Get payment from database
        payment = Payment.objects.get(merchant_order_id=merchant_order_id, user=request.user)

        # Check status with PhonePe
        phonepe_response = phonepe_service.get_order_status(merchant_order_id, details=False)

        if not phonepe_response.get("success"):
            return Response(
                {"error": "Failed to fetch payment status", "details": phonepe_response.get("error")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Prepare payment details for response/storage
        payment_details_list = []
        for pd in phonepe_response.get("payment_details", []):
            if hasattr(pd, "__dict__"):
                payment_details_list.append(pd.__dict__)
            else:
                payment_details_list.append(pd)

        # Prepare meta info for storage
        meta_info_dict = {}
        meta_info = phonepe_response.get("meta_info")
        if meta_info:
            if hasattr(meta_info, "__dict__"):
                meta_info_dict = meta_info.__dict__
            else:
                meta_info_dict = meta_info

        # Update payment status
        with transaction.atomic():
            payment_state = phonepe_response.get("state")

            if payment_state == "COMPLETED":
                payment.status = "completed"

                # Extract payment details
                if payment_details_list:
                    latest_payment = payment_details_list[0]
                    payment.phonepe_transaction_id = latest_payment.get("transaction_id", "")
                    payment.payment_mode = latest_payment.get("payment_mode", "")
                    payment.instrument_type = latest_payment.get("instrument_type", "")

                # Update related objects based on payment type
                if payment.payment_type in ["tournament_plan", "scrim_plan"] and payment.tournament:
                    payment.tournament.plan_payment_status = True
                    payment.tournament.plan_payment_id = merchant_order_id
                    payment.tournament.save()

                elif payment.payment_type == "entry_fee" and payment.registration:
                    payment.registration.payment_status = True
                    payment.registration.payment_id = merchant_order_id
                    payment.registration.save()

            elif payment_state == "FAILED":
                payment.status = "failed"
                payment.error_code = phonepe_response.get("error_code", "")
                payment.detailed_error_code = phonepe_response.get("detailed_error_code", "")

            # Store clean data
            payment.callback_data = {
                "order_id": phonepe_response.get("order_id"),
                "state": payment_state,
                "amount": phonepe_response.get("amount"),
                "expire_at": phonepe_response.get("expire_at"),
                "meta_info": meta_info_dict,
                "error_code": phonepe_response.get("error_code"),
                "detailed_error_code": phonepe_response.get("detailed_error_code"),
                "payment_details": payment_details_list,
            }
            payment.save()

        logger.info(f"Payment status checked: {merchant_order_id} - Status: {payment.status}")

        return Response(
            {
                "success": True,
                "merchant_order_id": merchant_order_id,
                "status": payment.status,
                "amount": str(payment.amount),
                "payment_type": payment.payment_type,
                "phonepe_state": payment_state,
                "payment_details": payment_details_list,
            },
            status=status.HTTP_200_OK,
        )

    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_payments(request):
    """
    List all payments for the authenticated user
    """
    try:
        payments = Payment.objects.filter(user=request.user).order_by("-created_at")
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error listing payments: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_refund(request):
    """
    Initiate a refund (Admin/Host only)

    Request Body:
    {
        "payment_id": 1,
        "amount": 299.00,
        "reason": "Tournament cancelled"
    }
    """
    # Check if user is staff or host
    if not (request.user.is_staff or hasattr(request.user, "host_profile")):
        return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

    serializer = InitiateRefundSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    try:
        payment = Payment.objects.get(id=data["payment_id"])

        # Generate unique refund ID
        merchant_refund_id = f"REF_{uuid4().hex[:16].upper()}"

        # Convert amount to paisa
        amount_paisa = int(data["amount"] * 100)

        # Create refund record
        with transaction.atomic():
            refund = Refund.objects.create(
                merchant_refund_id=merchant_refund_id,
                payment=payment,
                amount=data["amount"],
                amount_paisa=amount_paisa,
                reason=data.get("reason", ""),
                status="pending",
            )

            # Initiate refund with PhonePe
            phonepe_response = phonepe_service.initiate_refund(
                merchant_refund_id=merchant_refund_id,
                original_merchant_order_id=payment.merchant_order_id,
                amount=amount_paisa,
            )

            if not phonepe_response.get("success"):
                refund.status = "failed"
                refund.error_code = phonepe_response.get("error_code", "")
                refund.save()

                return Response(
                    {"error": "Failed to initiate refund", "details": phonepe_response.get("error")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Update refund with PhonePe response
            refund.phonepe_refund_id = phonepe_response.get("refund_id")
            refund.status = phonepe_response.get("state", "pending").lower()
            refund.callback_data = phonepe_response
            refund.save()

            logger.info(f"Refund initiated: {merchant_refund_id} for payment {payment.merchant_order_id}")

            return Response(
                {
                    "success": True,
                    "merchant_refund_id": merchant_refund_id,
                    "phonepe_refund_id": phonepe_response.get("refund_id"),
                    "state": phonepe_response.get("state"),
                    "amount": str(data["amount"]),
                },
                status=status.HTTP_200_OK,
            )

    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error initiating refund: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
def phonepe_callback(request):
    """
    PhonePe webhook callback handler

    This endpoint receives callbacks from PhonePe for payment/refund status updates
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # Get callback data
        authorization_header = request.headers.get("Authorization", "")
        callback_body = request.body.decode("utf-8")

        # Get configured credentials
        callback_username = config("PHONEPE_CALLBACK_USERNAME", default="")
        callback_password = config("PHONEPE_CALLBACK_PASSWORD", default="")

        if not callback_username or not callback_password:
            logger.warning("PhonePe callback credentials not configured")
            return JsonResponse({"error": "Callback not configured"}, status=500)

        # Validate callback
        validation_response = phonepe_service.validate_callback(
            username=callback_username,
            password=callback_password,
            authorization_header=authorization_header,
            callback_response_body=callback_body,
        )

        if not validation_response.get("success"):
            logger.error(f"Callback validation failed: {validation_response.get('error')}")
            return JsonResponse({"error": "Invalid callback"}, status=400)

        callback_type = validation_response.get("callback_type")
        callback_data = validation_response.get("callback_data")

        logger.info(f"Received PhonePe callback: Type={callback_type}")

        # Handle different callback types
        with transaction.atomic():
            # callback_data is now a dict with 'event' and 'payload' keys
            event_type = callback_data.get("event", "")
            payload = callback_data.get("payload", {})

            if event_type in ["checkout.order.completed", "checkout.order.failed"]:
                # Payment callback
                merchant_order_id = payload.get("merchantOrderId", "")

                try:
                    payment = Payment.objects.get(merchant_order_id=merchant_order_id)

                    if event_type == "checkout.order.completed":
                        payment.status = "completed"

                        # Update related objects
                        if payment.payment_type in ["tournament_plan", "scrim_plan"] and payment.tournament:
                            payment.tournament.plan_payment_status = True
                            payment.tournament.plan_payment_id = merchant_order_id
                            payment.tournament.save()

                        elif payment.payment_type == "entry_fee" and payment.registration:
                            payment.registration.payment_status = True
                            payment.registration.payment_id = merchant_order_id
                            payment.registration.save()

                    else:  # FAILED
                        payment.status = "failed"
                        payment.error_code = payload.get("errorCode", "")
                        payment.detailed_error_code = payload.get("detailedErrorCode", "")

                    payment.phonepe_order_id = payload.get("orderId", "")

                    # callback_data is already a dict
                    payment.callback_data = callback_data

                    payment.save()

                    logger.info(f"Payment updated from callback: {merchant_order_id} - Status: {payment.status}")

                except Payment.DoesNotExist:
                    logger.error(f"Payment not found for callback: {merchant_order_id}")

            elif event_type in ["pg.refund.completed", "pg.refund.failed", "pg.refund.accepted"]:
                # Refund callback
                merchant_refund_id = payload.get("merchantRefundId", "")

                try:
                    refund = Refund.objects.get(merchant_refund_id=merchant_refund_id)

                    if event_type == "pg.refund.completed":
                        refund.status = "completed"
                    elif event_type == "pg.refund.failed":
                        refund.status = "failed"
                        refund.error_code = payload.get("errorCode", "")
                        refund.detailed_error_code = payload.get("detailedErrorCode", "")
                    elif event_type == "pg.refund.accepted":
                        refund.status = "accepted"

                    refund.phonepe_refund_id = payload.get("refundId", "")

                    # callback_data is already a dict
                    refund.callback_data = callback_data

                    refund.save()

                    logger.info(f"Refund updated from callback: {merchant_refund_id} - Status: {refund.status}")

                except Refund.DoesNotExist:
                    logger.error(f"Refund not found for callback: {merchant_refund_id}")

        return JsonResponse({"success": True, "message": "Callback processed"}, status=200)

    except json.JSONDecodeError:
        logger.error("Invalid JSON in callback")
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)
