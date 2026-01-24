"""
Payment Views for PhonePe Integration
"""

import hashlib
import json
import logging
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from decouple import config
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import HostProfile, PlayerProfile, Team, TeamMember, User
from tournaments.models import Tournament, TournamentRegistration

from .models import Payment, Refund
from .serializers import InitiatePaymentSerializer, InitiateRefundSerializer, PaymentSerializer, PaymentStatusSerializer
from .services import phonepe_service

logger = logging.getLogger(__name__)


def convert_to_dict(obj):
    """
    Recursively convert PhonePe SDK objects to JSON-serializable dictionaries
    """
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, dict):
        return {k: convert_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_dict(item) for item in obj]
    elif hasattr(obj, "__dict__"):
        return {k: convert_to_dict(v) for k, v in obj.__dict__.items()}
    else:
        return str(obj)


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

        # Convert all PhonePe objects to dictionaries recursively
        payment_details_list = convert_to_dict(phonepe_response.get("payment_details", []))
        meta_info_dict = convert_to_dict(phonepe_response.get("meta_info"))

        # Update payment status
        with transaction.atomic():
            payment_state = phonepe_response.get("state")

            if payment_state == "COMPLETED":
                payment.status = "completed"

                # Extract payment details
                if payment_details_list and isinstance(payment_details_list, list) and len(payment_details_list) > 0:
                    latest_payment = payment_details_list[0]
                    if isinstance(latest_payment, dict):
                        payment.phonepe_transaction_id = latest_payment.get("transaction_id", "")
                        payment.payment_mode = latest_payment.get("payment_mode", "")
                        payment.instrument_type = latest_payment.get("instrument_type", "")

                # Create tournament/registration from pending_data
                if payment.payment_type in ["tournament_plan", "scrim_plan"] and payment.pending_data:
                    # Create tournament from pending data

                    tournament_data = payment.pending_data.copy()
                    host_id = tournament_data.pop("host_id", None)

                    # Convert datetime strings back to datetime objects
                    datetime_fields = ["registration_start", "registration_end", "tournament_start", "tournament_end"]
                    for field in datetime_fields:
                        if field in tournament_data and isinstance(tournament_data[field], str):
                            tournament_data[field] = datetime.fromisoformat(tournament_data[field])

                    # Convert date strings
                    if "tournament_date" in tournament_data and isinstance(tournament_data["tournament_date"], str):
                        tournament_data["tournament_date"] = datetime.fromisoformat(
                            tournament_data["tournament_date"]
                        ).date()

                    # Convert time strings
                    if "tournament_time" in tournament_data and isinstance(tournament_data["tournament_time"], str):
                        hour, minute, second = tournament_data["tournament_time"].split(":")
                        tournament_data["tournament_time"] = time(int(hour), int(minute), int(float(second)))

                    # Convert numeric fields back to Decimal
                    decimal_fields = ["entry_fee", "prize_pool", "plan_price"]
                    for field in decimal_fields:
                        if field in tournament_data and not isinstance(tournament_data[field], Decimal):
                            tournament_data[field] = Decimal(str(tournament_data[field]))

                    if host_id:
                        host = HostProfile.objects.get(id=host_id)
                        tournament = Tournament.objects.create(
                            host=host,
                            plan_payment_status=True,
                            plan_payment_id=merchant_order_id,
                            is_payment_pending=False,
                            payment_deadline=None,
                            **tournament_data,
                        )

                        # Link payment to tournament
                        payment.tournament = tournament
                        payment.pending_data = {}  # Clear pending data

                        logger.info(f"Tournament created from payment: {tournament.id} - {tournament.title}")

                        # Invalidate caches
                        cache.delete("tournaments:list:all")
                        cache.delete(f"host:dashboard:{host.id}")

                elif payment.payment_type == "entry_fee" and payment.pending_data:
                    # Create registration from pending data

                    reg_data = payment.pending_data.copy()
                    tournament_id = reg_data.pop("tournament_id", None)
                    player_id = reg_data.pop("player_id", None)
                    team_id = reg_data.pop("team_id", None)
                    player_usernames = reg_data.pop("player_usernames", [])
                    team_name = reg_data.pop("team_name", "")
                    save_as_team = reg_data.pop("save_as_team", False)

                    if tournament_id and player_id:
                        tournament = Tournament.objects.get(id=tournament_id)
                        player = PlayerProfile.objects.get(id=player_id)

                        # Create team if needed (same logic as serializer)
                        team_instance = None
                        if team_id:
                            team_instance = Team.objects.get(id=team_id)
                        elif save_as_team:
                            team_instance = Team.objects.create(name=team_name, captain=player.user)
                            for username in player_usernames:
                                user_obj = User.objects.filter(username=username, user_type="player").first()
                                is_cap = username == player.user.username
                                TeamMember.objects.create(
                                    team=team_instance, username=username, user=user_obj, is_captain=is_cap
                                )
                        else:
                            team_instance = Team.objects.create(name=team_name, captain=player.user, is_temporary=True)

                        # Prepare team members data
                        team_members_data = []
                        for username in player_usernames:
                            user_obj = User.objects.filter(username=username, user_type="player").first()
                            team_members_data.append(
                                {
                                    "username": username,
                                    "is_registered": user_obj is not None,
                                    "player_id": user_obj.player_profile.id
                                    if user_obj and hasattr(user_obj, "player_profile")
                                    else None,
                                }
                            )

                        # Create registration
                        registration = TournamentRegistration.objects.create(
                            tournament=tournament,
                            player=player,
                            team=team_instance,
                            team_name=team_name,
                            team_members=team_members_data,
                            payment_status=True,
                            payment_id=merchant_order_id,
                            is_payment_pending=False,
                            payment_deadline=None,
                            **reg_data,
                        )

                        # Update participant count
                        tournament.current_participants += 1
                        tournament.save()

                        # Link payment to registration
                        payment.registration = registration
                        payment.pending_data = {}  # Clear pending data

                        logger.info(f"Registration created from payment: {registration.id}")

                        # Invalidate caches
                        cache.delete("tournaments:list:all")
                        cache.delete(f"host:dashboard:{tournament.host.id}")

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_pending_payments(request):
    """
    List pending/failed payments for the authenticated user
    Shows payments that can be retried
    """
    try:
        # Get pending or failed payments that haven't expired
        payments = Payment.objects.filter(
            user=request.user, status__in=["pending", "failed"], payment_expires_at__gt=timezone.now()
        ).order_by("-created_at")

        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error listing pending payments: {str(e)}")
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
        # Get authorization header and body
        authorization_header = request.headers.get("Authorization", "")
        callback_body = request.body.decode("utf-8")

        # Get configured credentials
        callback_username = config("PHONEPE_CALLBACK_USERNAME", default="")
        callback_password = config("PHONEPE_CALLBACK_PASSWORD", default="")

        if not callback_username or not callback_password:
            logger.warning("PhonePe callback credentials not configured")
            return JsonResponse({"error": "Callback not configured"}, status=500)

        # Manually validate Authorization header (SHA256 of username:password)
        expected_auth = hashlib.sha256(f"{callback_username}:{callback_password}".encode()).hexdigest()

        if authorization_header != expected_auth:
            logger.error(f"Callback authorization failed. Expected: {expected_auth}, Got: {authorization_header}")
            return JsonResponse({"error": "Unauthorized"}, status=401)

        # Parse JSON body directly
        callback_data = json.loads(callback_body)
        event_type = callback_data.get("event", "")
        payload = callback_data.get("payload", {})

        logger.info(f"Received PhonePe callback: Type={event_type}")

        # Handle different callback types
        with transaction.atomic():
            if event_type in ["checkout.order.completed", "checkout.order.failed"]:
                # Payment callback
                merchant_order_id = payload.get("merchantOrderId", "")

                try:
                    payment = Payment.objects.get(merchant_order_id=merchant_order_id)

                    if event_type == "checkout.order.completed":
                        payment.status = "completed"

                        # Create tournament/registration from pending_data (same logic as check_payment_status)
                        if payment.payment_type in ["tournament_plan", "scrim_plan"] and payment.pending_data:
                            tournament_data = payment.pending_data.copy()
                            host_id = tournament_data.pop("host_id", None)

                            # Convert datetime strings back to datetime objects
                            datetime_fields = [
                                "registration_start",
                                "registration_end",
                                "tournament_start",
                                "tournament_end",
                            ]
                            for field in datetime_fields:
                                if field in tournament_data and isinstance(tournament_data[field], str):
                                    tournament_data[field] = datetime.fromisoformat(tournament_data[field])

                            # Convert date strings
                            if "tournament_date" in tournament_data and isinstance(
                                tournament_data["tournament_date"], str
                            ):
                                tournament_data["tournament_date"] = datetime.fromisoformat(
                                    tournament_data["tournament_date"]
                                ).date()

                            # Convert time strings
                            if "tournament_time" in tournament_data and isinstance(
                                tournament_data["tournament_time"], str
                            ):
                                hour, minute, second = tournament_data["tournament_time"].split(":")
                                tournament_data["tournament_time"] = time(int(hour), int(minute), int(float(second)))

                            # Convert numeric fields back to Decimal
                            decimal_fields = ["entry_fee", "prize_pool", "plan_price"]
                            for field in decimal_fields:
                                if field in tournament_data and not isinstance(tournament_data[field], Decimal):
                                    tournament_data[field] = Decimal(str(tournament_data[field]))

                            if host_id:
                                host = HostProfile.objects.get(id=host_id)
                                tournament = Tournament.objects.create(
                                    host=host,
                                    plan_payment_status=True,
                                    plan_payment_id=merchant_order_id,
                                    is_payment_pending=False,
                                    payment_deadline=None,
                                    **tournament_data,
                                )

                                # Link payment to tournament
                                payment.tournament = tournament
                                payment.pending_data = {}  # Clear pending data

                                logger.info(f"Tournament created from webhook: {tournament.id} - {tournament.title}")

                                # Invalidate caches
                                cache.delete("tournaments:list:all")
                                cache.delete(f"host:dashboard:{host.id}")

                        elif payment.payment_type == "entry_fee" and payment.pending_data:
                            reg_data = payment.pending_data.copy()
                            tournament_id = reg_data.pop("tournament_id", None)
                            player_id = reg_data.pop("player_id", None)
                            team_id = reg_data.pop("team_id", None)
                            player_usernames = reg_data.pop("player_usernames", [])
                            team_name = reg_data.pop("team_name", "")
                            save_as_team = reg_data.pop("save_as_team", False)

                            if tournament_id and player_id:
                                tournament = Tournament.objects.get(id=tournament_id)
                                player = PlayerProfile.objects.get(id=player_id)

                                # Create team if needed
                                team_instance = None
                                if team_id:
                                    team_instance = Team.objects.get(id=team_id)
                                elif save_as_team:
                                    team_instance = Team.objects.create(name=team_name, captain=player.user)
                                    for username in player_usernames:
                                        user_obj = User.objects.filter(username=username, user_type="player").first()
                                        is_cap = username == player.user.username
                                        TeamMember.objects.create(
                                            team=team_instance, username=username, user=user_obj, is_captain=is_cap
                                        )
                                else:
                                    team_instance = Team.objects.create(
                                        name=team_name, captain=player.user, is_temporary=True
                                    )

                                # Prepare team members data
                                team_members_data = []
                                for username in player_usernames:
                                    user_obj = User.objects.filter(username=username, user_type="player").first()
                                    team_members_data.append(
                                        {
                                            "username": username,
                                            "is_registered": user_obj is not None,
                                            "player_id": user_obj.player_profile.id
                                            if user_obj and hasattr(user_obj, "player_profile")
                                            else None,
                                        }
                                    )

                                # Create registration
                                registration = TournamentRegistration.objects.create(
                                    tournament=tournament,
                                    player=player,
                                    team=team_instance,
                                    team_name=team_name,
                                    team_members=team_members_data,
                                    payment_status=True,
                                    payment_id=merchant_order_id,
                                    is_payment_pending=False,
                                    payment_deadline=None,
                                    **reg_data,
                                )

                                # Update participant count
                                tournament.current_participants += 1
                                tournament.save()

                                # Link payment to registration
                                payment.registration = registration
                                payment.pending_data = {}  # Clear pending data

                                logger.info(f"Registration created from webhook: {registration.id}")

                                # Invalidate caches
                                cache.delete("tournaments:list:all")
                                cache.delete(f"host:dashboard:{tournament.host.id}")

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
