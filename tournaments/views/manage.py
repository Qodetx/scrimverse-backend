import json
import logging
from datetime import datetime, time as dtime
from decimal import Decimal
from datetime import date, datetime, time
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time

from rest_framework import generics, parsers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, Notification, TeamMember
from payments.models import Payment, PlanPricing
from payments.services import phonepe_service
from tournaments.models import Match, Tournament, TournamentRegistration
from tournaments.serializers import TournamentSerializer, TournamentRegistrationSerializer
from tournaments.tasks import send_tournament_created_email_task
from tournaments.views.permissions import IsHostUser

logger = logging.getLogger(__name__)


class TournamentCreateView(generics.CreateAPIView):
    """
    Host creates a tournament - initiates payment flow
    POST /api/tournaments/create/
    Returns payment redirect URL instead of creating tournament immediately
    """

    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def create(self, request, *args, **kwargs):
        """Validate tournament data and initiate payment"""
        logger.debug(
            f"Tournament creation request - Host: {request.user.id}, Event mode: {request.data.get('event_mode')}"
        )

        # Clean empty file fields (FormData sends empty strings for missing files)
        data = request.data.copy()

        # Remove empty file fields to prevent validation errors
        for file_field in ["banner_image", "tournament_file"]:
            if file_field in data:
                value = data[file_field]
                if value == "" or value == "null" or (isinstance(value, str) and not value):
                    data.pop(file_field)
                elif hasattr(value, "size") and value.size == 0:
                    data.pop(file_field)

        # Remap frontend field `match_count` → model field `max_matches` if present
        if "match_count" in data and "max_matches" not in data:
            data["max_matches"] = data["match_count"]

        # Parse `match_maps` from JSON string if sent as FormData string
        # Pull it out before serializer sees it, apply after save
        match_maps_parsed = None
        if "match_maps" in data and isinstance(data["match_maps"], str):
            try:
                match_maps_parsed = json.loads(data["match_maps"])
                data._mutable = True
                data.pop("match_maps")
                data._mutable = False
            except (json.JSONDecodeError, ValueError):
                pass

        # Validate the data using serializer
        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            logger.error(f"[DEBUG] Serializer validation errors: {serializer.errors}")
            return Response(serializer.errors, status=400)

        # Get validated data but DON'T create tournament yet
        validated_data = serializer.validated_data
        plan_type = validated_data.get("plan_type", "basic")
        event_mode = validated_data.get("event_mode", "TOURNAMENT")

        # Get dynamic price from database (or fallback to defaults)
        amount = PlanPricing.get_price(event_mode, plan_type)

        # BYPASS: Skip payment for all hosts (temporary - remove this line to re-enable payments)
        amount = 0

        # ✅ CHECK IF FREE PLAN (amount <= 0)
        if amount <= 0:
            # Skip payment, create tournament directly
            logger.info(f"Free plan detected ({plan_type}), creating tournament directly")

            # Create tournament immediately
            tournament = serializer.save(
                host=request.user.host_profile, plan_payment_status=True, plan_payment_id="FREE_PLAN"
            )

            if match_maps_parsed is not None:
                tournament.match_maps = match_maps_parsed
                tournament.save(update_fields=["match_maps"])

            logger.info(f"Tournament created (free plan): {tournament.id} - {tournament.title}")

            # Invalidate caches
            cache.delete("tournaments:list:all")
            cache.delete(f"host:dashboard:{request.user.host_profile.id}")

            # Send tournament created email task
            try:
                send_tournament_created_email_task.delay(
                    host_email=request.user.email,
                    host_name=request.user.username,
                    tournament_name=tournament.title,
                    game_name=tournament.game_name,
                    start_date=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                    max_participants=tournament.max_participants,
                    plan_type=f"{plan_type.title()} - {event_mode.title()}",
                    tournament_url=f"{settings.FRONTEND_URL}/tournaments/{tournament.id}",
                    tournament_manage_url=f"{settings.FRONTEND_URL}/tournaments/{tournament.id}/manage",
                )
                logger.info(f"Tournament created email task queued for {request.user.email}")
            except Exception as e:
                logger.error(f"Failed to queue tournament created email task: {str(e)}")

            return Response(
                {
                    "success": True,
                    "message": "Tournament created successfully (Free Plan)",
                    "tournament_id": tournament.id,
                    "payment_required": False,  # Signal to frontend to skip payment
                    "plan_type": plan_type,
                    "amount": 0,
                },
                status=200,
            )

        # PAID PLAN - Continue with payment flow
        # Generate unique merchant order ID
        merchant_order_id = f"ORD_{uuid4().hex[:16].upper()}"

        # Convert amount to paisa
        amount_paisa = int(amount * 100)

        # Prepare redirect URL
        frontend_url = settings.FRONTEND_URL
        redirect_url = f"{frontend_url}/host/dashboard?payment_status=check&order_id={merchant_order_id}"

        # Store tournament data as JSON (serialize files as paths if they exist)
        pending_tournament_data = {}
        # Fields to exclude (we set these explicitly when creating the tournament)
        excluded_fields = {"plan_payment_status", "plan_payment_id"}

        for key, value in validated_data.items():
            if key in excluded_fields:
                continue  # Skip fields we'll set explicitly
            if hasattr(value, "name"):  # File field
                pending_tournament_data[key] = value.name
            elif hasattr(value, "id"):  # Foreign key
                pending_tournament_data[key] = value.id
            elif isinstance(value, Decimal):
                pending_tournament_data[key] = float(value)
            elif isinstance(value, (datetime, date)):
                pending_tournament_data[key] = value.isoformat()
            elif isinstance(value, time):
                pending_tournament_data[key] = value.isoformat()
            else:
                pending_tournament_data[key] = value

        # Add host ID
        pending_tournament_data["host_id"] = request.user.host_profile.id

        # Prepare metadata - udf3 has 256 char limit, so store tournament data separately
        payment_type = "scrim_plan" if event_mode == "SCRIM" else "tournament_plan"
        meta_info = {
            "udf1": str(request.user.id),
            "udf2": payment_type,
            "udf3": payment_type,  # Just store payment type (within 256 char limit)
            "udf4": plan_type,
            "udf5": merchant_order_id,
            "tournament_data": pending_tournament_data,  # Store actual data here (not sent to PhonePe)
        }

        # Create payment record
        try:
            payment = Payment.objects.create(
                merchant_order_id=merchant_order_id,
                payment_type=payment_type,
                amount=amount,
                amount_paisa=amount_paisa,
                user=request.user,
                host_profile=request.user.host_profile,
                status="pending",
                meta_info=meta_info,
            )

            # Initiate payment with PhonePe
            phonepe_response = phonepe_service.initiate_payment(
                amount=amount_paisa,
                redirect_url=redirect_url,
                merchant_order_id=merchant_order_id,
                meta_info_dict=meta_info,
                message=f"Payment for {validated_data.get('title', 'Tournament')} - {plan_type.title()} Plan",
                expire_after=43200,  # 12 hours
                disable_payment_retry=False,
            )

            if not phonepe_response.get("success"):
                payment.status = "failed"
                payment.error_code = phonepe_response.get("error_code", "")
                payment.save()

                return Response(
                    {"error": "Failed to initiate payment", "details": phonepe_response.get("error")},
                    status=500,
                )

            # Update payment with PhonePe response
            payment.phonepe_order_id = phonepe_response.get("order_id")
            payment.redirect_url = phonepe_response.get("redirect_url")
            payment.save()

            logger.info(f"Payment initiated for tournament creation: {merchant_order_id}")

            return Response(
                {
                    "success": True,
                    "message": "Please complete payment to create tournament",
                    "merchant_order_id": merchant_order_id,
                    "phonepe_order_id": phonepe_response.get("order_id"),
                    "redirect_url": phonepe_response.get("redirect_url"),
                    "amount": float(amount),
                    "plan_type": plan_type,
                    "payment_required": True,  # Signal to frontend to open iframe
                },
                status=200,
            )

        except Exception as e:
            logger.error(f"Error initiating tournament payment: {str(e)}")
            return Response({"error": "Internal server error"}, status=500)


class TournamentUpdateView(generics.UpdateAPIView):
    """
    Host updates their tournament
    PUT/PATCH /api/tournaments/<id>/update/
    Invalidates cache on update
    """

    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        # Host can only update their own tournaments
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def perform_update(self, serializer):
        serializer.save()
        # Invalidate cache
        cache.delete("tournaments:list:all")


class TournamentDeleteView(generics.DestroyAPIView):
    """
    Host deletes their tournament
    DELETE /api/tournaments/<id>/delete/
    Invalidates cache on deletion
    """

    queryset = Tournament.objects.all()
    permission_classes = [IsHostUser]

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def perform_destroy(self, instance):
        instance.delete()
        # Invalidate cache
        cache.delete("tournaments:list:all")


class BulkScheduleUpdateView(APIView):
    """Bulk update scheduling fields on matches for a tournament (Host only).

    PUT /api/tournaments/<pk>/bulk-schedule/

    Expected payload: [
        {"match_id": 101, "scheduled_date": "2026-02-10", "scheduled_time": "18:30:00", "map_name": "Erangel"},
        ...
    ]
    """

    permission_classes = [IsHostUser]

    def put(self, request, pk, *args, **kwargs):
        data = request.data

        # Accept either a top-level JSON array or an object containing a 'schedules' array
        if isinstance(data, list):
            data_list = data
        elif isinstance(data, dict) and isinstance(data.get("schedules"), list):
            data_list = data.get("schedules")
        else:
            # Sometimes DRF may parse body as a string or other form; attempt to parse raw body
            try:
                raw = request.body.decode("utf-8")
                parsed = json.loads(raw) if raw else None
                if isinstance(parsed, list):
                    data_list = parsed
                elif isinstance(parsed, dict) and isinstance(parsed.get("schedules"), list):
                    data_list = parsed.get("schedules")
                else:
                    return Response({"error": "Expected a list of match updates"}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({"error": "Expected a list of match updates"}, status=status.HTTP_400_BAD_REQUEST)

        updated = []
        errors = []

        # Verify tournament exists and ownership
        try:
            tournament = Tournament.objects.get(id=pk)
        except Tournament.DoesNotExist:
            return Response({"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND)

        if tournament.host != request.user.host_profile:
            return Response({"error": "You do not have permission to modify this tournament"}, status=403)

        for idx, item in enumerate(data_list):
            match_id = item.get("match_id") or item.get("id")
            if not match_id:
                errors.append({"index": idx, "error": "match_id is required"})
                continue

            try:
                match = Match.objects.get(id=match_id)
            except Match.DoesNotExist:
                errors.append({"index": idx, "match_id": match_id, "error": "Match not found"})
                continue

            # Ensure match belongs to tournament and host
            if match.group.tournament.id != tournament.id:
                errors.append({"index": idx, "match_id": match_id, "error": "Match does not belong to this tournament"})
                continue

            # Parse and set fields
            sd = item.get("scheduled_date")
            st = item.get("scheduled_time")
            map_name = item.get("map_name")

            if sd is not None:
                parsed_date = parse_date(sd) if isinstance(sd, str) else sd
                if parsed_date is None:
                    errors.append({"index": idx, "match_id": match_id, "error": "Invalid scheduled_date"})
                    continue
                match.scheduled_date = parsed_date

            if st is not None:
                parsed_time = parse_time(st) if isinstance(st, str) else st
                if parsed_time is None:
                    errors.append({"index": idx, "match_id": match_id, "error": "Invalid scheduled_time"})
                    continue
                match.scheduled_time = parsed_time

            if map_name is not None:
                match.map_name = str(map_name)

            # Save the match
            try:
                match.save()
                updated.append(match.id)
            except Exception as e:
                errors.append({"index": idx, "match_id": match_id, "error": str(e)})

        # If we updated any matches, optionally update tournament start to earliest scheduled match
        if updated:
            try:
                matches_qs = Match.objects.filter(group__tournament=tournament, scheduled_date__isnull=False).order_by('scheduled_date', 'scheduled_time')
                if matches_qs.exists():
                    earliest = matches_qs.first()
                    sd = earliest.scheduled_date
                    st = earliest.scheduled_time or dtime.min
                    # Combine into a timezone-aware datetime if possible
                    try:
                        dt = datetime.combine(sd, st)
                        if timezone.is_naive(dt):
                            dt = timezone.make_aware(dt, timezone.get_current_timezone())
                        tournament.tournament_start = dt
                    except Exception:
                        # Fallback: set naive datetime
                        tournament.tournament_start = datetime.combine(sd, st)

                    # Also set helper date/time fields if present on model
                    try:
                        tournament.tournament_date = sd
                        tournament.tournament_time = st
                    except Exception:
                        pass

                    tournament.save()
            except Exception:
                # Don't fail the whole request if updating tournament_start errors
                pass

        result = {"updated_count": len(updated), "updated_ids": updated, "errors": errors}
        return Response(result, status=status.HTTP_200_OK)


class ManageTournamentView(generics.RetrieveAPIView):
    """
    Get tournament management data (host only)
    GET /api/tournaments/<pk>/manage/
    Returns tournament with all registrations
    """

    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Get all registrations for this tournament
        registrations = TournamentRegistration.objects.filter(tournament=instance)
        registration_serializer = TournamentRegistrationSerializer(registrations, many=True)

        return Response(
            {
                "tournament": serializer.data,
                "registrations": registration_serializer.data,
            }
        )


class UpdateTournamentFieldsView(generics.UpdateAPIView):
    """
    Update specific tournament fields (restricted - host only)
    PUT/PATCH /api/tournaments/<pk>/update-fields/
    Only allows updating: title, description, rules, rounds, round_names
    """

    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsHostUser]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def get_queryset(self):
        host_profile = HostProfile.objects.get(user=self.request.user)
        return Tournament.objects.filter(host=host_profile)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # Only allow editing upcoming tournaments — once started, configuration is locked.
        # Exception: live_link can always be updated (host may add stream link after tournament starts).
        request_fields = set(request.data.keys())
        live_link_only = request_fields <= {"live_link"}
        if instance.status != "upcoming" and not live_link_only:
            return Response(
                {"detail": "Tournament configuration can only be edited while the tournament is upcoming."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Allow updating all fields that are available during creation
        allowed_fields = [
            "title",
            "description",
            "rules",
            "round_names",
            "rounds",
            "round_dates",
            "tournament_date",
            "tournament_time",
            "tournament_start",
            "tournament_end",
            "registration_start",
            "registration_end",
            "max_participants",
            "entry_fee",
            "prize_pool",
            "prize_distribution",
            "special_awards",
            "coupon_distribution",
            "placement_points",
            "banner_image",
            "tournament_file",
            "plan_type",
            "live_link",
        ]
        data = request.data.copy()

        # Filter to only allowed fields
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Handle file uploads
        if "banner_image" in request.FILES:
            filtered_data["banner_image"] = request.FILES["banner_image"]
            # Pass the instance's plan_type so validate_banner_image sees the correct plan
            filtered_data["plan_type"] = instance.plan_type

        if "tournament_file" in request.FILES:
            filtered_data["tournament_file"] = request.FILES["tournament_file"]

        # Handle JSON fields
        for json_field in ("round_names", "rounds", "round_dates", "prize_distribution", "placement_points", "special_awards", "coupon_distribution"):
            if json_field in filtered_data:
                try:
                    if isinstance(filtered_data[json_field], str):
                        filtered_data[json_field] = json.loads(filtered_data[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass  # Let serializer validation handle invalid JSON

        # Handle live_link: URLField rejects empty strings, so save via queryset.update after serializer
        live_link = filtered_data.pop('live_link', None)

        logger.info(f"Updating tournament {instance.id} with fields: {list(filtered_data.keys())}")
        if "rounds" in filtered_data:
            logger.info(f"New rounds data: {filtered_data['rounds']}")
        if "round_names" in filtered_data:
            logger.info(f"New round_names data: {filtered_data['round_names']}")
        if "round_dates" in filtered_data:
            logger.info(f"New round_dates data: {filtered_data['round_dates']}")

        serializer = self.get_serializer(instance, data=filtered_data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # Save live_link via direct SQL update so serializer.save() can't overwrite it
        if live_link is not None:
            Tournament.objects.filter(pk=instance.pk).update(
                live_link=live_link if live_link else None
            )

        cache.delete("tournaments:list:all")
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)


class UpdateTeamStatusView(generics.GenericAPIView):
    """
    Host updates team registration status (confirm/reject)
    PATCH /api/tournaments/<tournament_id>/registrations/<registration_id>/status/
    Body: {"status": "confirmed"} or {"status": "rejected"}

    Manages participant count:
    - Confirming a pending team: no change (already counted)
    - Confirming a rejected team: increase count
    - Rejecting a pending/confirmed team: decrease count
    """

    permission_classes = [IsHostUser]

    def patch(self, request, tournament_id, registration_id):
        logger.debug(
            f"Update team status request - Tournament: {tournament_id}, Registration: {registration_id}, New status: {request.data.get('status')}"  # noqa E501
        )

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        try:
            registration = TournamentRegistration.objects.get(id=registration_id, tournament=tournament)
        except TournamentRegistration.DoesNotExist:
            return Response({"error": "Registration not found"}, status=404)

        new_status = request.data.get("status")
        if new_status not in ["confirmed", "rejected", "pending"]:
            return Response({"error": "Invalid status. Must be 'confirmed', 'rejected', or 'pending'"}, status=400)

        old_status = registration.status

        # Update participant count based on status change
        if old_status != new_status:
            # Rejecting a team that was pending or confirmed -> decrease count
            if new_status == "rejected" and old_status in ["pending", "confirmed"]:
                if tournament.current_participants > 0:
                    tournament.current_participants -= 1
                    tournament.save(update_fields=["current_participants"])

            # Confirming a team that was rejected -> increase count
            elif new_status == "confirmed" and old_status == "rejected":
                if tournament.current_participants < tournament.max_participants:
                    tournament.current_participants += 1
                    tournament.save(update_fields=["current_participants"])
                else:
                    return Response({"error": "Tournament is full. Cannot confirm more teams."}, status=400)

        registration.status = new_status
        registration.save()

        logger.info(
            f"Team status updated - Registration: {registration.id}, Old: {old_status}, New: {new_status}, Tournament: {tournament.id}"  # noqa E501
        )

        return Response(
            {
                "message": f"Team status updated to {new_status}",
                "registration_id": registration.id,
                "status": registration.status,
                "current_participants": tournament.current_participants,
                "max_participants": tournament.max_participants,
            }
        )


class StartTournamentView(generics.GenericAPIView):
    """
    Host explicitly starts the tournament
    POST /api/tournaments/<tournament_id>/start/

    Validates:
    - Pending teams will be automatically confirmed upon starting
    - Tournament status is 'upcoming'

    Actions:
    - Changes status to 'ongoing'
    - Sets current_round to 1
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        logger.debug(f"Start tournament request - Tournament: {tournament_id}, Host: {request.user.id}")

        try:
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        except Tournament.DoesNotExist:
            return Response({"error": "Tournament not found"}, status=404)

        # Validate tournament status
        if tournament.status != "upcoming":
            return Response({"error": f"Cannot start tournament. Current status: {tournament.status}"}, status=400)

        # Check if starting early
        now = timezone.now()
        if now < tournament.tournament_start:
            return Response(
                {
                    "error": f"Cannot start tournament early. Scheduled start: {tournament.tournament_start.strftime('%B %d, %Y at %I:%M %p')}"  # noqa: E501
                },
                status=400,
            )

        # Auto-confirm any pending teams before starting
        TournamentRegistration.objects.filter(tournament=tournament, status="pending").update(status="confirmed")

        # Update tournament
        tournament.status = "ongoing"

        # If Round 1 was pre-configured, keep it as pre_configured and leave current_round=0
        # so the host must explicitly click "Start Round 1" to activate it and notify players.
        # Otherwise, set round 1 as ongoing immediately.
        if not tournament.round_status:
            tournament.round_status = {}
        round1_status = tournament.round_status.get("1")
        is_preconfigured = (
            isinstance(round1_status, dict) and round1_status.get("status") == "pre_configured"
        )
        if is_preconfigured:
            tournament.current_round = 0
        else:
            tournament.current_round = 1
            tournament.round_status["1"] = "ongoing"

        tournament.save(update_fields=["status", "current_round", "round_status"])

        logger.info(f"Tournament started - ID: {tournament.id}, Title: {tournament.title}")

        return Response(
            {
                "message": "Tournament started successfully",
                "status": tournament.status,
                "current_round": tournament.current_round,
                "scheduled_start": tournament.tournament_start.isoformat() if tournament.tournament_start else None,
            }
        )


class EndTournamentView(generics.GenericAPIView):
    """
    End tournament (mark as completed)
    POST /api/tournaments/<tournament_id>/end/
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        # Check if all rounds are completed (warning only, not blocking)
        all_rounds_completed = True
        if tournament.round_status and len(tournament.round_status) > 0:
            def _is_completed(val):
                if isinstance(val, dict):
                    return val.get("status") == "completed"
                return val == "completed"
            all_rounds_completed = all(_is_completed(s) for s in tournament.round_status.values())

        # End tournament regardless of round status (host decision)
        tournament.status = "completed"
        tournament.current_round = 0
        tournament.save(update_fields=["status", "current_round"])
        cache.delete("tournaments:list:all")

        logger.info(
            f"Tournament ended - ID: {tournament.id}, Title: {tournament.title}, All rounds completed: {all_rounds_completed}"  # noqa E501
        )

        from tournaments.models import Match, TournamentRegistration
        from tournaments.tasks import send_tournament_completed_email_task, update_leaderboard

        # Get tournament statistics
        total_participants = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed").count()
        total_matches = Match.objects.filter(group__tournament=tournament).count()

        # Get winner information
        winner_name = "TBD"
        runner_up_name = "TBD"
        if tournament.winners:
            # Get the final round winner
            final_round_key = str(len(tournament.rounds)) if tournament.rounds else "1"
            winner_id = tournament.winners.get(final_round_key)
            if winner_id:
                try:
                    winner_reg = TournamentRegistration.objects.get(id=winner_id)
                    winner_name = winner_reg.team_name or winner_reg.player.user.username
                except TournamentRegistration.DoesNotExist:
                    pass

        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        tournament_manage_url = f"{frontend_url}/host/tournaments/{tournament.id}/manage"

        send_tournament_completed_email_task.delay(
            host_email=tournament.host.user.email,
            host_name=tournament.host.user.username,
            tournament_name=tournament.title,
            completed_at=timezone.now().strftime("%B %d, %Y at %I:%M %p"),
            total_participants=total_participants,
            total_matches=total_matches,
            winner_name=winner_name,
            runner_up_name=runner_up_name,
            total_registrations=total_participants,
            results_published=bool(tournament.winners),
            tournament_manage_url=tournament_manage_url,
        )

        logger.info(f"Tournament completed email sent to host: {tournament.host.user.email}")

        # Notify all confirmed registered players — "Tournament Ended" then "Winner Declared"
        try:
            registrations = TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).select_related("team", "player__user")

            # Collect unique user IDs across all registered teams/players
            notified_user_ids = set()
            for reg in registrations:
                if reg.team_id:
                    # Team-based registration — notify all team members
                    member_user_ids = TeamMember.objects.filter(
                        team_id=reg.team_id, user__isnull=False
                    ).values_list("user_id", flat=True)
                    notified_user_ids.update(member_user_ids)
                elif reg.player_id:
                    # Solo registration — notify the player directly
                    notified_user_ids.add(reg.player.user_id)

            ended_notifications = []
            winner_notifications = []
            for user_id in notified_user_ids:
                ended_notifications.append(
                    Notification(
                        user_id=user_id,
                        type="tournament_result",
                        title="Tournament Ended",
                        message=f"{tournament.title} has ended.",
                        related_id=tournament.id,
                        related_type="tournament",
                    )
                )
                if winner_name != "TBD":
                    winner_notifications.append(
                        Notification(
                            user_id=user_id,
                            type="tournament_result",
                            title="Winner Declared",
                            message=f"{winner_name} has won {tournament.title}!",
                            related_id=tournament.id,
                            related_type="tournament",
                        )
                    )

            if ended_notifications:
                Notification.objects.bulk_create(ended_notifications)
                logger.info(
                    f"Tournament end notifications sent - Tournament: {tournament.id}, Players notified: {len(ended_notifications)}"
                )
            if winner_notifications:
                Notification.objects.bulk_create(winner_notifications)
                logger.info(
                    f"Winner notifications sent - Tournament: {tournament.id}, Winner: {winner_name}, Players notified: {len(winner_notifications)}"
                )
        except Exception as e:
            logger.error(f"Failed to send tournament end notifications: {e}", exc_info=True)

        # Trigger leaderboard update asynchronously
        update_leaderboard.delay()

        message = "Tournament ended successfully"
        if not all_rounds_completed:
            message += " (Note: Not all rounds were completed)"

        return Response(
            {
                "message": message,
                "status": tournament.status,
                "all_rounds_completed": all_rounds_completed,
            }
        )
