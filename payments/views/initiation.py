"""
Payment initiation and status checking views.
Handles creating payment orders, checking status, and listing payments.
"""
import logging
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Sum

from accounts.models import HostProfile, Notification, PlayerProfile, Team, TeamMember, User
from payments.models import Payment
from payments.serializers import (
    InitiatePaymentSerializer,
    PaymentSerializer,
    PaymentStatusSerializer,
)
from payments.services import phonepe_service
from tournaments.models import Tournament, TournamentRegistration, RoundScore
from tournaments.services_registration import process_successful_registration
from tournaments.tasks import (
    send_registration_limit_reached_email_task,
    send_tournament_created_email_task,
    send_tournament_registration_email_task,
)
from decouple import config

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
        # Quick config check: ensure PhonePe credentials are configured
        client_id = config("CLIENT_ID", default="").strip()
        client_secret = config("CLIENT_SECRET", default="").strip()
        if not client_id or client_id == "dymmy" or not client_secret:
            logger.error("PhonePe credentials not configured (CLIENT_ID/CLIENT_SECRET missing or default).")
            return Response(
                {"error": "Payment gateway not configured"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        frontend_url = settings.FRONTEND_URL
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

                # Create tournament/registration from meta_info
                if payment.payment_type in ["tournament_plan", "scrim_plan"]:
                    # Get tournament data from meta_info (stored separately, not in udf3)
                    tournament_data = payment.meta_info.get("tournament_data", {})
                    if tournament_data:
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
                            # Check if tournament already exists (e.g. created by webhook)
                            tournament = Tournament.objects.filter(plan_payment_id=merchant_order_id).first()

                            if not tournament:
                                # Remove fields that we're setting explicitly to avoid duplicates
                                tournament_data.pop("plan_payment_status", None)

                                host = HostProfile.objects.get(id=host_id)
                                tournament = Tournament.objects.create(
                                    host=host,
                                    plan_payment_status=True,
                                    plan_payment_id=merchant_order_id,
                                    **tournament_data,
                                )
                                logger.info(
                                    f"Tournament created from payment check: {tournament.id} - {tournament.title}"
                                )
                            # Ensure link exists and is saved
                            if not payment.tournament:
                                payment.tournament = tournament
                                payment.save()

                            logger.info(f"Tournament linked to payment check: {tournament.id}")

                            # Send tournament created email to host
                            frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
                            tournament_url = f"{frontend_url}/tournaments/{tournament.id}"
                            tournament_manage_url = f"{frontend_url}/host/tournaments/{tournament.id}/manage"
                            start_date = tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p")
                            event_type = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"

                            send_tournament_created_email_task.delay(
                                host_email=host.user.email,
                                host_name=host.user.username,
                                tournament_name=tournament.title,
                                game_name=tournament.game_name,
                                start_date=start_date,
                                max_participants=tournament.max_participants,
                                plan_type=f"{tournament.plan_type} - {event_type}",
                                tournament_url=tournament_url,
                                tournament_manage_url=tournament_manage_url,
                            )

                            logger.info(f"Tournament created email sent to host: {host.user.email}")

                            # Clear tournament_data from meta_info (no longer needed)
                            payment.meta_info.pop("tournament_data", None)
                            payment.save()

                            # Invalidate caches
                            cache.delete("tournaments:list:all")
                            cache.delete(f"host:dashboard:{host.id}")

                elif payment.payment_type == "entry_fee":
                    # ===== INVITE-BASED FLOW (NEW) =====
                    # Check if this is an invite-based registration (registration_id in udf4)
                    registration_id = payment.meta_info.get("udf4")
                    if registration_id:
                        try:
                            registration = TournamentRegistration.objects.get(id=int(registration_id))
                            # If this registration has temp_teammate_emails, it's invite-based
                            if registration.temp_teammate_emails:
                                # Call the service to handle invite-based post-payment logic
                                result = process_successful_registration(registration, merchant_order_id)
                                logger.info(f"✅ Invite-based registration processed: {registration.id}")

                                # Ensure links in payment
                                payment.registration = registration
                                payment.save()

                                # Small success notification
                                cache.delete("tournaments:list:all")
                                cache.delete(f"host:dashboard:{registration.tournament.host.id}")
                        except TournamentRegistration.DoesNotExist:
                            logger.warning(f"Registration {registration_id} not found for invite-flow")
                        except Exception as e:
                            logger.error(f"Error processing invite-based registration: {str(e)}")

                    # ===== LEGACY FLOW (OLD) =====
                    # Get registration data from meta_info (stored separately, not in udf3)
                    reg_data = payment.meta_info.get("registration_data", {})
                    if reg_data:
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
                                # Per-member temp logic: team itself is permanent. Captain's
                                # membership is temp only if they already have a perm team
                                # for this game.
                                from accounts.team_helpers import determine_member_temp_status
                                cap_temp, cap_deadline = determine_member_temp_status(
                                    player.user, tournament.game_name, tournament
                                )
                                team_instance = Team.objects.create(
                                    name=team_name,
                                    captain=player.user,
                                    is_temporary=False,
                                    game=tournament.game_name,
                                    linked_tournament=tournament,
                                )
                                TeamMember.objects.create(
                                    team=team_instance,
                                    user=player.user,
                                    username=player.user.username,
                                    is_captain=True,
                                    is_temporary=cap_temp,
                                    conversion_deadline=cap_deadline,
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

                            # Check if registration already exists
                            registration = TournamentRegistration.objects.filter(payment_id=merchant_order_id).first()

                            if not registration:
                                # Create registration
                                registration = TournamentRegistration.objects.create(
                                    tournament=tournament,
                                    player=player,
                                    team=team_instance,
                                    team_name=team_name,
                                    team_members=team_members_data,
                                    payment_status=True,
                                    payment_id=merchant_order_id,
                                    **reg_data,
                                )
                                # Update participant count
                                tournament.current_participants += 1
                                tournament.save()
                                logger.info(f"Registration created from payment check: {registration.id}")
                            # Ensure link exists
                            if not payment.registration:
                                payment.registration = registration
                                payment.save()

                            logger.info(f"Registration linked to payment: {registration.id}")

                            # Send registration success email to all team members
                            frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
                            tournament_url = f"{frontend_url}/tournaments/{tournament.id}"
                            start_date = tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p")
                            event_type = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"

                            # Send to captain (player who registered)
                            send_tournament_registration_email_task.delay(
                                user_email=player.user.email,
                                user_name=player.user.username,
                                tournament_name=tournament.title,
                                game_name=tournament.game_name,
                                start_date=start_date,
                                registration_id=str(registration.id),
                                tournament_url=tournament_url,
                                team_name=team_name,
                            )

                            # Send to all team members
                            for member_data in team_members_data:
                                if member_data.get("is_registered") and member_data.get("player_id"):
                                    try:
                                        member_player = PlayerProfile.objects.get(id=member_data["player_id"])
                                        send_tournament_registration_email_task.delay(
                                            user_email=member_player.user.email,
                                            user_name=member_player.user.username,
                                            tournament_name=tournament.title,
                                            game_name=tournament.game_name,
                                            start_date=start_date,
                                            registration_id=str(registration.id),
                                            tournament_url=tournament_url,
                                            team_name=team_name,
                                        )
                                        logger.info(
                                            f"Registration email sent to team member: {member_player.user.email}"
                                        )
                                    except PlayerProfile.DoesNotExist:
                                        pass

                            logger.info(f"Registration success emails queued for {len(team_members_data) + 1} players")

                            # Notify host of new registration
                            try:
                                Notification.objects.create(
                                    user=tournament.host.user,
                                    type='new_registration',
                                    title='New Team Registered',
                                    message=f'Team "{team_name}" has registered for your tournament "{tournament.title}".',
                                    related_id=tournament.id,
                                    related_type='tournament',
                                )
                            except Exception as e:
                                logger.warning(f"Failed to create host registration notification: {e}")

                            # Notify captain (and team members) that payment & registration is confirmed
                            try:
                                event_label = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"
                                notif_message = f'Your payment for "{tournament.title}" was successful. Registration is confirmed!'
                                notif_title = f'{event_label} Registration Confirmed'
                                # Notify captain
                                Notification.objects.create(
                                    user=player.user,
                                    type='payment_confirmed',
                                    title=notif_title,
                                    message=notif_message,
                                    related_id=tournament.id,
                                    related_type='tournament',
                                )
                                # Notify team members
                                for member_data in team_members_data:
                                    if member_data.get("is_registered") and member_data.get("player_id"):
                                        try:
                                            member_player = PlayerProfile.objects.get(id=member_data["player_id"])
                                            Notification.objects.create(
                                                user=member_player.user,
                                                type='payment_confirmed',
                                                title=notif_title,
                                                message=notif_message,
                                                related_id=tournament.id,
                                                related_type='tournament',
                                            )
                                        except PlayerProfile.DoesNotExist:
                                            pass
                            except Exception as e:
                                logger.warning(f"Failed to create payment confirmation notifications: {e}")

                            # Check if tournament is full - send slots filled email to host
                            registration_count = TournamentRegistration.objects.filter(
                                tournament=tournament, status="confirmed"
                            ).count()

                            if registration_count >= tournament.max_participants:
                                send_registration_limit_reached_email_task.delay(
                                    host_email=tournament.host.user.email,
                                    host_name=tournament.host.user.username,
                                    tournament_name=tournament.title,
                                    total_registrations=registration_count,
                                    max_participants=tournament.max_participants,
                                    start_date=tournament.tournament_start.strftime("%B %d, %Y"),
                                    tournament_manage_url=f"{frontend_url}/host/tournaments/{tournament.id}/manage",
                                )
                                logger.info(f"Slots filled email sent to host: {tournament.host.user.email}")
                                # Notify host that slots are full
                                try:
                                    Notification.objects.create(
                                        user=tournament.host.user,
                                        type='slots_full',
                                        title='Tournament Slots Full',
                                        message=f'All {tournament.max_participants} slots for "{tournament.title}" have been filled.',
                                        related_id=tournament.id,
                                        related_type='tournament',
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to create slots_full notification: {e}")

                            # Clear registration_data from meta_info (no longer needed)
                            payment.meta_info.pop("registration_data", None)
                            payment.save()

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

        # Ensure we have the latest links before returning
        payment.refresh_from_db()

        return Response(
            {
                "success": True,
                "merchant_order_id": merchant_order_id,
                "status": payment.status,
                "amount": str(payment.amount),
                "payment_type": payment.payment_type,
                "tournament_id": payment.tournament.id if payment.tournament else None,
                "registration_id": payment.registration.id if payment.registration else None,
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
def player_earnings(request):
    """
    Calculate prize money earned by the authenticated player from completed tournaments.

    Logic:
    1. Find all completed tournaments where this player's team is registered
    2. For each tournament, determine team's final placement from the last round's standings
    3. Map placement to prize_distribution JSON to get prize amount
    4. Return earnings list + summary stats
    """
    try:
        user = request.user

        # Get all registrations for this player in completed tournaments
        registrations = TournamentRegistration.objects.filter(
            player__user=user,
            status="confirmed",
            tournament__status="completed",
        ).select_related("tournament", "team")

        earnings = []
        total_earned = 0
        total_won = 0  # Count of tournaments where player earned prize money

        for reg in registrations:
            tournament = reg.tournament
            prize_dist = tournament.prize_distribution or {}

            if not prize_dist:
                continue

            # Determine total rounds
            round_count = 1
            if tournament.rounds and isinstance(tournament.rounds, list):
                round_count = len(tournament.rounds)
            elif tournament.current_round:
                round_count = tournament.current_round

            # Get final round standings — all teams sorted by total_points desc
            final_scores = RoundScore.objects.filter(
                tournament=tournament,
                round_number=round_count,
            ).order_by("-total_points")

            if not final_scores.exists():
                # Fallback: try round 1 (single-round tournaments / scrims)
                final_scores = RoundScore.objects.filter(
                    tournament=tournament,
                    round_number=1,
                ).order_by("-total_points")

            if not final_scores.exists():
                continue

            # Find this team's position in final standings
            position = None
            for idx, score in enumerate(final_scores, start=1):
                if score.team_id == reg.id:
                    position = idx
                    break

            if position is None:
                continue

            # Map position to prize_distribution key
            # prize_distribution can have keys like "1st", "2nd", "3rd" or "1", "2", "3"
            position_keys = [
                f"{position}",  # "1", "2", "3"
            ]
            # Add ordinal suffix versions
            if position == 1:
                position_keys.append("1st")
            elif position == 2:
                position_keys.append("2nd")
            elif position == 3:
                position_keys.append("3rd")
            else:
                position_keys.append(f"{position}th")

            prize_amount = 0
            for key in position_keys:
                if key in prize_dist:
                    try:
                        prize_amount = float(prize_dist[key])
                    except (ValueError, TypeError):
                        pass
                    break

            if prize_amount > 0:
                total_earned += prize_amount
                total_won += 1
                earnings.append({
                    "id": f"earning-{reg.id}",
                    "tournament_id": tournament.id,
                    "tournament_title": tournament.title,
                    "game_name": tournament.game_name or "",
                    "amount": prize_amount,
                    "position": position,
                    "date": tournament.tournament_end.isoformat() if tournament.tournament_end else tournament.updated_at.isoformat(),
                    "type": "winnings",
                })

        # Sort by date descending
        earnings.sort(key=lambda e: e["date"], reverse=True)

        return Response(
            {
                "total_earned": total_earned,
                "total_won": total_won,
                "earnings": earnings,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Error calculating player earnings: {str(e)}")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def host_transactions(request):
    """
    Returns entry-fee payment data grouped by tournament for the authenticated host.
    Each tournament includes total_revenue, scrimverse_fee (10%), team_count, and
    a list of individual payment rows.
    """
    try:
        host_profile = HostProfile.objects.get(user=request.user)
    except HostProfile.DoesNotExist:
        return Response({"error": "Host profile not found"}, status=status.HTTP_403_FORBIDDEN)

    tournaments = Tournament.objects.filter(host=host_profile).order_by("-created_at")
    result = []

    for t in tournaments:
        payments = (
            Payment.objects.filter(
                tournament=t,
                payment_type="entry_fee",
                status="completed",
            )
            .select_related("registration", "user")
            .order_by("created_at")
        )

        payment_rows = []
        for p in payments:
            team_name = ""
            if p.registration:
                team_name = p.registration.team_name or ""
            if not team_name:
                team_name = p.user.username if p.user else "Unknown"
            payment_rows.append({
                "team_name": team_name,
                "amount": str(p.amount),
                "paid_at": p.completed_at or p.created_at,
            })

        total_revenue = float(sum(p.amount for p in payments))
        result.append({
            "id": t.id,
            "title": t.title,
            "game_name": t.game_name or "",
            "entry_fee": str(t.entry_fee or 0),
            "total_revenue": str(total_revenue),
            "scrimverse_fee": str(round(total_revenue * 0.10, 2)),
            "team_count": len(payment_rows),
            "payments": payment_rows,
        })

    return Response({"tournaments": result})
