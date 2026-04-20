"""
PhonePe webhook callback handler.
Receives async payment/refund status updates from PhonePe and processes them.
"""
import hashlib
import json
import logging
import traceback
from datetime import datetime, time
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from decouple import config

from accounts.models import HostProfile, Notification, PlayerProfile, Team, TeamMember, User
from payments.models import Payment, Refund
from tournaments.models import Tournament, TournamentRegistration
from tournaments.services_registration import process_successful_registration
from tournaments.tasks import (
    send_registration_limit_reached_email_task,
    send_tournament_created_email_task,
    send_tournament_registration_email_task,
)

logger = logging.getLogger(__name__)


@csrf_exempt
def phonepe_callback(request):
    """
    PhonePe webhook callback handler

    This endpoint receives callbacks from PhonePe for payment/refund status updates
    """
    logger.info("=" * 80)
    logger.info("PhonePe Callback Received")
    logger.info("=" * 80)

    if request.method != "POST":
        logger.warning(f"Invalid method: {request.method}")
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # Get authorization header and body
        authorization_header = request.headers.get("Authorization", "")
        callback_body = request.body.decode("utf-8")

        logger.info(f"Authorization Header: {authorization_header[:20]}...")
        logger.info(f"Callback Body: {callback_body}")

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

        logger.info(f"Event Type: {event_type}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")

        # Handle different callback types
        with transaction.atomic():
            if event_type in ["checkout.order.completed", "checkout.order.failed"]:
                # Payment callback
                merchant_order_id = payload.get("merchantOrderId", "")
                logger.info(f"Processing payment callback for order: {merchant_order_id}")

                try:
                    payment = Payment.objects.get(merchant_order_id=merchant_order_id)
                    logger.info(f"Found payment: {payment.id}, Type: {payment.payment_type}, Status: {payment.status}")

                    if event_type == "checkout.order.completed":
                        payment.status = "completed"
                        logger.info("Payment marked as completed")

                        # Create tournament/registration from meta_info
                        if payment.payment_type in ["tournament_plan", "scrim_plan"]:
                            logger.info("Processing tournament/scrim creation")
                            # Get tournament data from meta_info (stored separately, not in udf3)
                            tournament_data = payment.meta_info.get("tournament_data", {})
                            logger.info(f"Tournament data found: {bool(tournament_data)}")
                            logger.info(
                                f"Tournament data keys: {list(tournament_data.keys()) if tournament_data else 'None'}"
                            )

                            if tournament_data:
                                host_id = tournament_data.pop("host_id", None)
                                logger.info(f"Host ID: {host_id}")

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
                                    tournament_data["tournament_time"] = time(
                                        int(hour), int(minute), int(float(second))
                                    )

                                # Convert numeric fields back to Decimal
                                decimal_fields = ["entry_fee", "prize_pool", "plan_price"]
                                for field in decimal_fields:
                                    if field in tournament_data and not isinstance(tournament_data[field], Decimal):
                                        tournament_data[field] = Decimal(str(tournament_data[field]))

                                if host_id:
                                    logger.info(f"Creating tournament with data: {list(tournament_data.keys())}")

                                    # IDEMPOTENCY CHECK: Check if tournament already exists for this order
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
                                            f"✅ Tournament created successfully: {tournament.id} - {tournament.title}"
                                        )
                                    else:
                                        logger.info(f"Tournament already exists for order: {merchant_order_id}")

                                    # Link payment to tournament
                                    payment.tournament = tournament

                                    logger.info(f"Tournament linked from webhook: {tournament.id} - {tournament.title}")

                                    # Send tournament created email to host
                                    frontend_url = config(
                                        "CORS_ALLOWED_ORIGINS", default="http://localhost:3000"
                                    ).split(",")[0]
                                    tournament_url = f"{frontend_url}/tournaments/{tournament.id}"
                                    tournament_manage_url = f"{frontend_url}/host/tournaments/{tournament.id}/manage"
                                    start_date = tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p")
                                    event_type_label = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"

                                    send_tournament_created_email_task.delay(
                                        host_email=host.user.email,
                                        host_name=host.user.username,
                                        tournament_name=tournament.title,
                                        game_name=tournament.game_name,
                                        start_date=start_date,
                                        max_participants=tournament.max_participants,
                                        plan_type=f"{tournament.plan_type} - {event_type_label}",
                                        tournament_url=tournament_url,
                                        tournament_manage_url=tournament_manage_url,
                                    )

                                    logger.info(
                                        f"Tournament created email sent from webhook to host: {host.user.email}"
                                    )

                                    # Clear tournament_data from meta_info (no longer needed and contains Decimals)
                                    payment.meta_info.pop("tournament_data", None)

                                # Invalidate caches
                                cache.delete("tournaments:list:all")
                                cache.delete(f"host:dashboard:{host.id}")

                        elif payment.payment_type == "entry_fee":
                            # ===== INVITE-BASED FLOW (NEW) =====
                            registration_id = payment.meta_info.get("udf4")
                            if registration_id:
                                try:
                                    registration = TournamentRegistration.objects.get(id=int(registration_id))
                                    if registration.temp_teammate_emails:
                                        result = process_successful_registration(registration, merchant_order_id)
                                        logger.info(f"✅ Invite-based registration processed from webhook: {registration.id}")

                                        payment.registration = registration
                                        cache.delete("tournaments:list:all")
                                        cache.delete(f"host:dashboard:{registration.tournament.host.id}")
                                except TournamentRegistration.DoesNotExist:
                                    logger.warning(f"Registration {registration_id} not found for invite-flow (webhook)")
                                except Exception as e:
                                    logger.error(f"Error processing invite-based registration (webhook): {str(e)}")

                            # ===== LEGACY FLOW (OLD) =====
                            # Get registration data from meta_info (stored separately, not in udf3)
                            # Initialize legacy variables to avoid UnboundLocalError when reg_data is empty
                            tournament_id = None
                            player_id = None
                            team_id = None
                            player_usernames = []
                            team_name = ""
                            save_as_team = False

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
                                        name=team_name,
                                        captain=player.user,
                                        is_temporary=True,
                                        linked_tournament=tournament
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
                                # IDEMPOTENCY CHECK: Check if registration already exists
                                registration = TournamentRegistration.objects.filter(
                                    payment_id=merchant_order_id
                                ).first()

                                if not registration:
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
                                    logger.info(f"Registration created from webhook: {registration.id}")
                                else:
                                    logger.info(f"Registration already exists for order: {merchant_order_id}")

                                # Link payment to registration
                                payment.registration = registration
                                logger.info(f"Registration linked from webhook: {registration.id}")

                                # Send registration success email to all team members
                                frontend_url = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(
                                    ","
                                )[0]
                                tournament_url = f"{frontend_url}/tournaments/{tournament.id}"
                                start_date = tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p")

                                # Send to captain
                                send_tournament_registration_email_task.delay(
                                    user_email=player.user.email,
                                    user_name=player.user.username,
                                    tournament_name=tournament.tournament_name,
                                    game_name=tournament.game,
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
                                                tournament_name=tournament.tournament_name,
                                                game_name=tournament.game,
                                                start_date=start_date,
                                                registration_id=str(registration.id),
                                                tournament_url=tournament_url,
                                                team_name=team_name,
                                            )
                                        except PlayerProfile.DoesNotExist:
                                            pass

                                logger.info(
                                    f"Registration emails queued from webhook for {len(team_members_data) + 1} players"
                                )

                                # Notify host of new registration
                                try:
                                    Notification.objects.create(
                                        user=tournament.host.user,
                                        type='new_registration',
                                        title='New Team Registered',
                                        message=f'Team "{team_name}" has registered for your tournament "{tournament.tournament_name}".',
                                        related_id=tournament.id,
                                        related_type='tournament',
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to create host registration notification: {e}")

                                # Notify captain (and team members) that payment & registration is confirmed
                                try:
                                    event_label = "Scrim" if tournament.event_mode == "SCRIM" else "Tournament"
                                    notif_message = f'Your payment for "{tournament.tournament_name}" was successful. Registration is confirmed!'
                                    notif_title = f'{event_label} Registration Confirmed'
                                    Notification.objects.create(
                                        user=player.user,
                                        type='payment_confirmed',
                                        title=notif_title,
                                        message=notif_message,
                                        related_id=tournament.id,
                                        related_type='tournament',
                                    )
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
                                        tournament_name=tournament.tournament_name,
                                        total_registrations=registration_count,
                                        max_participants=tournament.max_participants,
                                        start_date=tournament.tournament_start.strftime("%B %d, %Y"),
                                        tournament_manage_url=f"{frontend_url}/host/tournaments/{tournament.id}/manage",
                                    )
                                    logger.info(
                                        f"Slots filled email sent from webhook to host: {tournament.host.user.email}"
                                    )
                                    # Notify host that slots are full
                                    try:
                                        Notification.objects.create(
                                            user=tournament.host.user,
                                            type='slots_full',
                                            title='Tournament Slots Full',
                                            message=f'All {tournament.max_participants} slots for "{tournament.tournament_name}" have been filled.',
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

        logger.info("=" * 80)
        logger.info("✅ Callback processed successfully")
        logger.info("=" * 80)
        return JsonResponse({"success": True, "message": "Callback processed"}, status=200)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in callback: {str(e)}")
        logger.error(f"Callback body: {request.body.decode('utf-8')}")
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ Error processing callback: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        logger.error("=" * 80)
        return JsonResponse({"error": "Internal server error"}, status=500)
