import csv
import io
import logging
from uuid import uuid4

from decouple import config
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import HostProfile, PlayerProfile, Team, TeamMember, User
from accounts.notification_utils import should_notify
from payments.models import Payment
from payments.services import phonepe_service
from tournaments.models import Tournament, TournamentRegistration
from tournaments.serializers import TournamentRegistrationSerializer
from tournaments.tasks import (
    send_tournament_registration_email_task,
    update_host_dashboard_stats,
)
from tournaments.views.permissions import IsHostUser, IsPlayerUser

logger = logging.getLogger(__name__)


class TournamentRegistrationInitiateView(APIView):
    """
    Initiate tournament registration with email-based team invites.

    This is the FIRST STEP in the new invite-based registration flow:
    - Captain enters team name and invites 3 teammates via email
    - Registration record is created with status='pending_payment'
    - No payment initiated yet, just stores the registration data
    - Frontend will then proceed to payment page

    POST /api/tournaments/<tournament_id>/register-init/

    Request:
    {
        "team_name": "Alpha Squad",
        "teammate_emails": ["player2@example.com", "player3@example.com", "player4@example.com"]
    }
    """

    permission_classes = [IsPlayerUser]

    def post(self, request, tournament_id):
        """Initialize a registration with email invites."""

        # Get serializer context
        serializer_context = {
            'request': request,
            'tournament_id': tournament_id
        }

        # Validate input using the serializer
        from tournaments.serializers import TournamentRegistrationInitSerializer
        serializer = TournamentRegistrationInitSerializer(data=request.data, context=serializer_context)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Get validated data
        validated_data = serializer.validated_data
        team_name = validated_data['team_name']
        invite_mode = validated_data.get('invite_mode', 'email')
        # Each mode stores its own validated data — no cross-mode resolution
        teammate_emails = validated_data.get('teammate_emails', [])   # email mode
        original_phones = validated_data.get('teammate_phones', [])   # phone mode
        teammate_users = validated_data.get('teammate_users', [])     # username mode

        try:
            # Get player profile
            player_profile = request.user.player_profile

            # Get tournament
            tournament = Tournament.objects.get(id=tournament_id)

            # For free tournaments, create the Team now so registration.team is linked.
            # Per per-member temp logic: the team itself is created as permanent. Only
            # members who already had a perm team for this game get a temporary
            # membership with a 48h convert-or-decline window.
            team = None
            if float(tournament.entry_fee) == 0:
                from accounts.models import Team as TeamModel, TeamMember as TeamMemberModel
                from accounts.team_helpers import determine_member_temp_status

                captain_temp, captain_deadline = determine_member_temp_status(
                    request.user, tournament.game_name, tournament
                )

                team = TeamModel.objects.create(
                    name=team_name,
                    captain=request.user,
                    # Team-level flag stays False for new teams; per-member flag is the
                    # source of truth going forward. Legacy temp teams pre-migration
                    # are unaffected.
                    is_temporary=False,
                    linked_tournament=tournament,
                    game=tournament.game_name,
                )
                # Add captain as a team member (with the right temp flag)
                TeamMemberModel.objects.get_or_create(
                    team=team,
                    user=request.user,
                    defaults={
                        'username': request.user.username,
                        'is_captain': True,
                        'is_temporary': captain_temp,
                        'conversion_deadline': captain_deadline,
                    }
                )

            # Build the initial invited_members_status dict using the mode-appropriate contact keys
            if invite_mode == 'phone':
                contact_list = original_phones
            elif invite_mode == 'username':
                contact_list = [u.username for u in teammate_users]
            else:
                contact_list = teammate_emails

            # For temp_teammate_emails we store only email-mode emails (field name is legacy)
            stored_emails = teammate_emails if invite_mode == 'email' else []

            # Build initial team_members with captain always first
            initial_team_members = [{
                'username': request.user.username,
                'player_id': player_profile.id,
                'is_registered': True,
            }]

            # Create TournamentRegistration with status 'pending'
            registration = TournamentRegistration.objects.create(
                tournament=tournament,
                player=player_profile,
                team=team,
                team_name=team_name,
                status='pending',  # Using 'pending' as interim status
                payment_status=False,
                temp_teammate_emails=stored_emails,
                is_team_created=False,
                team_members=initial_team_members,
                invited_members_status={c: {'status': 'pending', 'username': None} for c in contact_list}
            )

            logger.info(
                f"Tournament registration initiated - Player: {request.user.id}, "
                f"Tournament: {tournament_id}, Registration: {registration.id}"
            )

            # If tournament is free, confirm registration immediately and send invites
            if float(tournament.entry_fee) == 0:
                from django.db import transaction
                from accounts.models import TeamJoinRequest
                from tournaments.tasks import send_team_invite_emails_task

                try:
                    with transaction.atomic():
                        # Re-check slot availability under lock to prevent race condition
                        from django.db.models import F
                        locked_t = Tournament.objects.select_for_update().get(id=tournament.id)
                        if locked_t.current_participants >= locked_t.max_participants:
                            raise ValidationError({"error": "Tournament is full."})

                        # Mark registration as confirmed immediately
                        registration.payment_status = True
                        registration.status = 'confirmed'
                        registration.save()

                        # Update tournament participants count atomically
                        Tournament.objects.filter(id=tournament.id).update(
                            current_participants=F('current_participants') + 1
                        )
                        tournament.refresh_from_db(fields=['current_participants'])

                    # Build team_members snapshot and create TeamJoinRequest records
                    # Each invite mode is fully independent — no cross-mode resolution.
                    team_members = []
                    invited_partners = []
                    from accounts.models import Notification

                    team = registration.team
                    if not team:
                        team, _ = Team.objects.get_or_create(
                            name=registration.team_name,
                            captain=player_profile.user,
                            defaults={'is_temporary': False},
                        )

                    if invite_mode == 'phone':
                        # Phone mode: phones are already normalised (10-digit) by the serializer
                        for phone in original_phones:
                            invite_token = str(uuid4())
                            invite_expires = timezone.now() + timezone.timedelta(days=7)

                            TeamJoinRequest.objects.create(
                                team=team,
                                player=None,  # unknown until user accepts
                                status='pending',
                                request_type='invite',
                                invite_type='phone',
                                phone_number=phone,
                                invite_token=invite_token,
                                invite_expires_at=invite_expires,
                                tournament_registration=registration,
                            )

                            team_members.append({
                                'phone': phone,
                                'username': None,
                                'player_id': None,
                                'is_registered': False,
                            })

                            # Send SMS
                            try:
                                from scrimverse.sms_utils import send_team_invite_sms
                                send_team_invite_sms(
                                    phone_number=f'+91{phone}',
                                    captain_name=request.user.username,
                                    team_name=team.name,
                                    invite_token=invite_token,
                                )
                            except Exception as e:
                                logger.error(f'Failed to send SMS to {phone}: {e}')

                    elif invite_mode == 'username':
                        # Username mode: teammate_users are resolved User objects from serializer
                        for user_obj in teammate_users:
                            invite_token = str(uuid4())
                            invite_expires = timezone.now() + timezone.timedelta(days=7)

                            TeamJoinRequest.objects.create(
                                team=team,
                                player=user_obj,
                                status='pending',
                                request_type='invite',
                                invite_type='username',
                                invite_token=invite_token,
                                invite_expires_at=invite_expires,
                                tournament_registration=registration,
                            )

                            team_members.append({
                                'username': user_obj.username,
                                'player_id': getattr(getattr(user_obj, 'player_profile', None), 'id', None),
                                'is_registered': True,
                            })

                            # In-app notification
                            if should_notify(user_obj, 'teamInvites'):
                                Notification.objects.create(
                                    user=user_obj,
                                    type='team_invite',
                                    title='Tournament Team Invite',
                                    message=f'{request.user.username} has invited you to join team "{team.name}" for tournament "{tournament.title}".',
                                    related_id=team.id,
                                    related_type='team',
                                )

                    else:
                        # Email mode: iterate validated email strings
                        for email in teammate_emails:
                            try:
                                member_user = User.objects.get(email__iexact=email, user_type='player')
                                player_id = getattr(getattr(member_user, 'player_profile', None), 'id', None)
                                username = member_user.username
                                is_registered = True
                            except Exception:
                                member_user = None
                                player_id = None
                                username = None
                                is_registered = False

                            invite_token = str(uuid4())
                            invite_expires = timezone.now() + timezone.timedelta(days=7)

                            TeamJoinRequest.objects.create(
                                team=team,
                                player=member_user if is_registered else None,
                                status='pending',
                                request_type='invite',
                                invite_type='email',
                                invited_email=email,
                                invite_token=invite_token,
                                invite_expires_at=invite_expires,
                                tournament_registration=registration,
                            )

                            team_members.append({
                                'email': email,
                                'username': username,
                                'player_id': player_id,
                                'is_registered': is_registered,
                            })

                            invited_partners.append({
                                'invited_email': email,
                                'invite_token': invite_token,
                                'invite_expires_at': invite_expires.strftime('%B %d, %Y'),
                            })

                    # Save team_members — captain always first, then invitees
                    captain_entry = {
                        'username': request.user.username,
                        'player_id': player_profile.id,
                        'is_registered': True,
                    }
                    try:
                        registration.team_members = [captain_entry] + team_members
                        registration.save()
                    except Exception as e:
                        logger.warning(f'Failed to save team_members for registration {registration.id}: {e}')

                    # Invalidate caches and update host stats
                    cache.delete('tournaments:list:all')
                    cache.delete(f'host:dashboard:{tournament.host.id}')
                    update_host_dashboard_stats.delay(tournament.host.id)

                    # Queue registration confirmation email to captain
                    try:
                        send_tournament_registration_email_task.delay(
                            user_email=player_profile.user.email,
                            user_name=player_profile.user.username,
                            tournament_name=tournament.title,
                            game_name=tournament.game_name,
                            start_date=tournament.tournament_start.strftime('%B %d, %Y at %I:%M %p'),
                            registration_id=str(registration.id),
                            tournament_url=f"{config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000').split(',')[0]}/tournaments/{tournament.id}",
                            team_name=registration.team_name,
                        )
                    except Exception as e:
                        logger.error(f'Failed to queue captain registration email: {e}')

                    # Queue invite emails only for email-mode invites
                    if invited_partners and invite_mode == 'email':
                        try:
                            send_team_invite_emails_task.delay(registration.team.id)
                        except Exception as e:
                            logger.error(f'Failed to queue invite emails for registration {registration.id}: {e}')

                    return Response({
                        'success': True,
                        'registration_id': registration.id,
                        'status': registration.status,
                        'team_name': registration.team_name,
                        'invited_contacts': contact_list,
                        'invite_mode': invite_mode,
                        'entry_fee': str(tournament.entry_fee),
                        'tournament_name': tournament.title,
                        'message': 'Registration confirmed for free tournament. Invitations sent to teammates.'
                    }, status=status.HTTP_201_CREATED)
                except Exception as e:
                    logger.error(f'Error confirming free registration: {e}')
                    # If something unexpected failed, fall back to returning the pending response

            return Response({
                'success': True,
                'registration_id': registration.id,
                'status': registration.status,
                'team_name': registration.team_name,
                'invited_contacts': contact_list,
                'entry_fee': str(tournament.entry_fee),
                'tournament_name': tournament.title,
                'message': 'Registration initiated. Proceed to payment to confirm.'
            }, status=status.HTTP_201_CREATED)

        except Tournament.DoesNotExist:
            return Response({'error': 'Tournament not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error initiating registration: {str(e)}")
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TournamentRegistrationCreateView(generics.CreateAPIView):
    """
    Player registers for a tournament as a team
    POST /api/tournaments/<tournament_id>/register/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def get_serializer_context(self):
        """Add tournament_id to serializer context"""
        context = super().get_serializer_context()
        context["tournament_id"] = self.kwargs["tournament_id"]
        return context

    def create(self, request, *args, **kwargs):
        """Override create to handle payment-required response status"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except ValidationError as e:
            # If it's a payment_required "error", return it as a 200 response
            if isinstance(e.detail, dict) and e.detail.get("payment_required"):
                return Response(e.detail, status=status.HTTP_200_OK)
            # Re-raise other validation errors
            raise

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        logger.debug(
            f"Tournament registration request - Player: {self.request.user.id}, Tournament: {self.kwargs['tournament_id']}"  # noqa E501
        )

        player_profile = PlayerProfile.objects.get(user=self.request.user)
        tournament_id = self.kwargs["tournament_id"]
        tournament = Tournament.objects.get(id=tournament_id)

        # Check registration window
        now = timezone.now()
        if now < tournament.registration_start:
            raise ValidationError({"error": "Registration has not started yet"})
        if now > tournament.registration_end:
            raise ValidationError({"error": "Registration has ended"})

        # Check if player has a rejected registration
        rejected_registration = TournamentRegistration.objects.filter(
            tournament=tournament, player=player_profile, status="rejected"
        ).first()

        if rejected_registration:
            raise ValidationError(
                {
                    "error": "You cannot re-register for this tournament. Your previous registration was rejected by the host."  # noqa
                }
            )

        # Check if tournament is full (only count confirmed registrations)
        confirmed_count = TournamentRegistration.objects.filter(tournament=tournament, status="confirmed").count()

        if confirmed_count >= tournament.max_participants:
            raise ValidationError({"error": "Tournament is full"})

        # Get player_usernames from validated data
        player_usernames = serializer.validated_data.get("player_usernames", [])
        team_id = serializer.validated_data.get("team_id")

        # Validate that the current user is in the team (only when not using existing team_id)
        if not team_id:
            current_username = self.request.user.username
            if current_username not in player_usernames:
                raise ValidationError({"player_usernames": "You must include your own username in the team"})

            # ✅ VALIDATE: All player_usernames must be registered players
            if player_usernames:
                invalid_usernames = []
                for username in player_usernames:
                    if username:
                        user_exists = User.objects.filter(username=username, user_type="player").exists()
                        if not user_exists:
                            invalid_usernames.append(username)

                if invalid_usernames:
                    raise ValidationError(
                        {
                            "player_usernames": f"The following players were not found: {', '.join(invalid_usernames)}. Only registered ScrimVerse players can join tournaments."  # noqa: E501
                        }
                    )

        # Check if any team member is already registered
        team_users = User.objects.filter(username__in=player_usernames, user_type="player").select_related(
            "player_profile"
        )
        team_player_ids = {user.player_profile.id for user in team_users if hasattr(user, "player_profile")}

        # Check existing CONFIRMED registrations (allow re-registration if only pending_payment)
        confirmed_registrations = TournamentRegistration.objects.filter(
            tournament=tournament,
            status="confirmed"
        )
        for registration in confirmed_registrations:
            if registration.team_members:
                registered_player_ids = {member.get("player_id") for member in registration.team_members if member.get("player_id")}
                overlapping_ids = team_player_ids & registered_player_ids
                if overlapping_ids:
                    registered_usernames = [
                        member.get("username")
                        for member in registration.team_members
                        if member.get("player_id") in overlapping_ids
                    ]
                    raise ValidationError(
                        {
                            "player_usernames": f"One or more players are already registered for this tournament: "
                            f"{', '.join(registered_usernames)}"
                        }
                    )

        # Check if entry fee is required
        if tournament.entry_fee > 0:
            # PAYMENT FLOW - Don't create registration yet
            pending_reg_data = {
                "tournament_id": tournament_id,
                "player_id": player_profile.id,
                "team_id": team_id,
                "player_usernames": player_usernames,
                "team_name": serializer.validated_data.get("team_name", ""),
                "save_as_team": serializer.validated_data.get("save_as_team", False),
            }

            # Add any other validated data
            for key, value in serializer.validated_data.items():
                if key not in [
                    "player_usernames",
                    "team_name",
                    "team_id",
                    "save_as_team",
                    "tournament_id",
                    "player_id",
                ]:
                    if hasattr(value, "id"):
                        pending_reg_data[key] = value.id
                    else:
                        pending_reg_data[key] = value

            # Generate unique merchant order ID
            merchant_order_id = f"ORD_{uuid4().hex[:16].upper()}"
            amount = tournament.entry_fee
            amount_paisa = int(amount * 100)

            # Prepare redirect URL
            frontend_url = settings.FRONTEND_URL
            redirect_url = f"{frontend_url}/player/dashboard?payment_status=check&order_id={merchant_order_id}"

            meta_info = {
                "udf1": str(self.request.user.id),
                "udf2": "entry_fee",
                "udf3": "entry_fee",
                "udf4": str(tournament_id),
                "udf5": merchant_order_id,
                "registration_data": pending_reg_data,
            }

            try:
                # Create payment record
                payment = Payment.objects.create(
                    merchant_order_id=merchant_order_id,
                    payment_type="entry_fee",
                    amount=amount,
                    amount_paisa=amount_paisa,
                    user=self.request.user,
                    player_profile=player_profile,
                    tournament=tournament,
                    status="pending",
                    meta_info=meta_info,
                )

                # Initiate payment with PhonePe
                phonepe_response = phonepe_service.initiate_payment(
                    amount=amount_paisa,
                    redirect_url=redirect_url,
                    merchant_order_id=merchant_order_id,
                    meta_info_dict=meta_info,
                    message=f"Entry fee for {tournament.title}",
                    expire_after=43200,  # 12 hours
                    disable_payment_retry=False,
                )

                if not phonepe_response.get("success"):
                    payment.status = "failed"
                    payment.error_code = phonepe_response.get("error_code", "")
                    payment.save()

                    raise ValidationError(
                        {"error": "Failed to initiate payment", "details": phonepe_response.get("error")}
                    )

                # Update payment with PhonePe response
                payment.phonepe_order_id = phonepe_response.get("order_id")
                payment.redirect_url = phonepe_response.get("redirect_url")
                payment.save()

                logger.info(f"Payment initiated for registration: {merchant_order_id}")

                raise ValidationError(
                    {
                        "payment_required": True,
                        "merchant_order_id": merchant_order_id,
                        "redirect_url": phonepe_response.get("redirect_url"),
                        "amount": float(amount),
                        "message": "Please complete payment to register",
                    }
                )

            except ValidationError:
                raise
            except Exception as e:
                logger.error(f"Error initiating registration payment: {str(e)}")
                raise ValidationError({"error": "Internal server error"})

        else:
            # NO PAYMENT REQUIRED - Create registration directly (atomic to prevent race condition)
            from django.db import transaction
            from django.db.models import F as F_expr
            with transaction.atomic():
                locked_t = Tournament.objects.select_for_update().get(id=tournament_id)
                confirmed_count_now = TournamentRegistration.objects.filter(
                    tournament=locked_t, status="confirmed"
                ).count()
                if confirmed_count_now >= locked_t.max_participants:
                    raise ValidationError({"error": "Tournament is full"})

                registration = serializer.save(player_id=player_profile.id, tournament_id=tournament_id)

                Tournament.objects.filter(id=tournament_id).update(
                    current_participants=F_expr('current_participants') + 1
                )
                tournament.refresh_from_db(fields=['current_participants'])

            logger.info(
                f"Registration created - ID: {registration.id}, Player: {player_profile.user.username}, Tournament: {tournament.title}, Team: {registration.team_name}"  # noqa E501
            )

            # Update participant count to accurate confirmed registrations
            tournament.current_participants = TournamentRegistration.objects.filter(
                tournament=tournament, status="confirmed"
            ).count()
            tournament.save(update_fields=["current_participants"])

            # Invalidate caches
            cache.delete("tournaments:list:all")
            cache.delete(f"host:dashboard:{tournament.host.id}")

            update_host_dashboard_stats.delay(tournament.host.id)

            # Send registration emails task
            try:
                # 1. Send to Captain
                send_tournament_registration_email_task.delay(
                    user_email=player_profile.user.email,
                    user_name=player_profile.user.username,
                    tournament_name=tournament.title,
                    game_name=tournament.game_name,
                    start_date=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                    registration_id=str(registration.id),
                    tournament_url=f"{config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000').split(',')[0]}/tournaments/{tournament.id}",  # noqa: E501
                    team_name=registration.team_name,
                )

                # 2. Send to Team Members
                if registration.team_members:
                    captain_name = player_profile.user.username
                    for member in registration.team_members:
                        member_username = member.get("username")
                        if member_username and member_username != captain_name:
                            try:
                                member_user = User.objects.get(username=member_username, user_type="player")
                                send_tournament_registration_email_task.delay(
                                    user_email=member_user.email,
                                    user_name=member_user.username,
                                    tournament_name=tournament.title,
                                    game_name=tournament.game_name,
                                    start_date=tournament.tournament_start.strftime("%B %d, %Y at %I:%M %p"),
                                    registration_id=str(registration.id),
                                    tournament_url=f"{config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000').split(',')[0]}/tournaments/{tournament.id}",  # noqa: E501
                                    team_name=registration.team_name,
                                )
                                # Flow B: in-app notification so non-captain sees
                                # RegistrationConfirmationModal on next login
                                from accounts.models import Notification
                                Notification.objects.get_or_create(
                                    user=member_user,
                                    type='registration_confirmed',
                                    related_id=registration.id,
                                    defaults={
                                        'title': 'Registration Confirmed!',
                                        'message': (
                                            f'Your team "{registration.team_name}" is registered '
                                            f'for "{tournament.title}".'
                                        ),
                                        'related_type': 'registration',
                                    },
                                )
                            except User.DoesNotExist:
                                continue
                logger.info("Tournament registration email tasks queued for captain and team members")
            except Exception as e:
                logger.error(f"Failed to queue tournament registration email tasks: {str(e)}")


class PlayerTournamentRegistrationsView(generics.ListAPIView):
    """
    Get all tournament registrations of a player
    GET /api/tournaments/my-registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsPlayerUser]

    def get_queryset(self):
        try:
            player_profile = PlayerProfile.objects.get(user=self.request.user)
            team_ids = TeamMember.objects.filter(user=self.request.user).values_list("team_id", flat=True)
            return (
                TournamentRegistration.objects.filter(Q(player=player_profile) | Q(team_id__in=team_ids))
                .distinct()
                .order_by("-registered_at")
            )
        except PlayerProfile.DoesNotExist:
            return TournamentRegistration.objects.none()


class PlayerPublicRegistrationsView(generics.ListAPIView):
    """
    Get all tournament registrations for any player publicly
    GET /api/tournaments/player/<player_id>/registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        player_id = self.kwargs["player_id"]

        try:
            player = PlayerProfile.objects.get(user_id=player_id)
            user = player.user
            team_ids = TeamMember.objects.filter(user=user).values_list("team_id", flat=True)

            queryset = TournamentRegistration.objects.filter(
                Q(player_id=player.id) | Q(team_id__in=team_ids)
            ).distinct()
        except PlayerProfile.DoesNotExist:
            return TournamentRegistration.objects.none()

        if self.request.query_params.get("confirmed") == "true":
            queryset = queryset.filter(status="confirmed")
        return queryset.order_by("-registered_at")


class TournamentRegistrationsView(generics.ListAPIView):
    """
    Get all registrations for a tournament (host only)
    GET /api/tournaments/<tournament_id>/registrations/
    """

    serializer_class = TournamentRegistrationSerializer
    permission_classes = [IsHostUser]

    def get_queryset(self):
        tournament_id = self.kwargs["tournament_id"]
        host_profile = HostProfile.objects.get(user=self.request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)
        return TournamentRegistration.objects.filter(tournament=tournament)


class TournamentRegistrationExportView(APIView):
    """
    Export tournament registrations as CSV (host only)
    GET /api/tournaments/<tournament_id>/registrations/export/
    """

    permission_classes = [IsHostUser]

    def get(self, request, tournament_id):
        """Export all registrations for a tournament as CSV"""
        try:
            # Verify host owns the tournament
            host_profile = HostProfile.objects.get(user=request.user)
            tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

            # Get all registrations
            registrations = TournamentRegistration.objects.filter(tournament=tournament).select_related(
                "player__user", "team"
            )

            # Create CSV in memory
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "User ID",
                    "User Name",
                    "Team ID",
                    "Team Name",
                    "Email",
                    "Phone Number",
                    "User Role",
                    "Status",
                ],
            )

            writer.writeheader()

            # Track added players to avoid duplicates
            added_players = set()

            for registration in registrations:
                player_user = registration.player.user
                team = registration.team
                team_id = team.id if team else "N/A"
                team_name = team.name if team else registration.team_name or "N/A"

                # Check if user is team captain
                is_captain = False
                if team:
                    team_captain = team.captain
                    is_captain = player_user.id == team_captain.id

                role = "Captain" if is_captain else "Member"

                # Create unique key to avoid duplicates
                player_key = (player_user.id, team.id if team else -1)

                if player_key not in added_players:
                    writer.writerow(
                        {
                            "User ID": player_user.id,
                            "User Name": player_user.username,
                            "Team ID": team_id,
                            "Team Name": team_name,
                            "Email": player_user.email,
                            "Phone Number": player_user.phone_number or "N/A",
                            "User Role": role,
                            "Status": registration.status,
                        }
                    )
                    added_players.add(player_key)

                # Add other team members if team exists
                if team:
                    team_members = TeamMember.objects.filter(team=team).select_related("user")
                    for member in team_members:
                        member_user = member.user
                        if member_user:
                            member_key = (member_user.id, team.id)
                            if member_key not in added_players:
                                member_role = "Captain" if member.is_captain else "Member"
                                writer.writerow(
                                    {
                                        "User ID": member_user.id,
                                        "User Name": member_user.username,
                                        "Team ID": team.id,
                                        "Team Name": team_name,
                                        "Email": member_user.email,
                                        "Phone Number": member_user.phone_number or "N/A",
                                        "User Role": member_role,
                                        "Status": registration.status,
                                    }
                                )
                                added_players.add(member_key)

            # Create HTTP response with CSV file
            response = HttpResponse(output.getvalue(), content_type="text/csv")
            response[
                "Content-Disposition"
            ] = f'attachment; filename="{tournament.title}_registrations.csv"'

            return response

        except Tournament.DoesNotExist:
            return Response({"error": "Tournament not found"}, status=404)
        except HostProfile.DoesNotExist:
            return Response({"error": "Host profile not found"}, status=404)
        except Exception as e:
            logger.error(f"Error exporting tournament registrations: {str(e)}")
            return Response({"error": "Failed to export registrations"}, status=500)


class SelectTeamsView(generics.GenericAPIView):
    """
    Select/eliminate teams for current round
    POST /api/tournaments/<tournament_id>/select-teams/
    Body: {"team_ids": [1, 2, 3], "action": "select"} or {"action": "eliminate"}
    """

    permission_classes = [IsHostUser]

    def post(self, request, tournament_id):
        logger.debug(
            f"Select teams request - Tournament: {tournament_id}, Action: {request.data.get('action')}, Host: {request.user.id}"  # noqa E501
        )

        host_profile = HostProfile.objects.get(user=request.user)
        tournament = Tournament.objects.get(id=tournament_id, host=host_profile)

        if tournament.current_round == 0:
            return Response({"error": "No round is currently active"}, status=400)

        action = request.data.get("action")  # "select" or "eliminate"
        team_ids = request.data.get("team_ids", [])

        if action not in ["select", "eliminate"]:
            return Response({"error": "Action must be 'select' or 'eliminate'"}, status=400)

        round_num = str(tournament.current_round)
        round_config = next((r for r in tournament.rounds if r["round"] == tournament.current_round), None)

        if not round_config:
            return Response({"error": "Round configuration not found"}, status=400)

        # Get current selected teams for this round
        if not tournament.selected_teams:
            tournament.selected_teams = {}
        if round_num not in tournament.selected_teams:
            tournament.selected_teams[round_num] = []

        current_selected = tournament.selected_teams[round_num]

        if action == "select":
            # Get selection limit: use qualifying_teams if set, otherwise max_teams
            qualifying_teams = round_config.get("qualifying_teams")
            max_teams = round_config.get("max_teams")

            # Determine selection limit
            if qualifying_teams and int(qualifying_teams) > 0:
                selection_limit = int(qualifying_teams)
            elif max_teams:
                selection_limit = int(max_teams)
            else:
                return Response({"error": "Team selection limit not set for this round"}, status=400)

            # Validate team IDs exist (allow pending and confirmed)
            registrations = TournamentRegistration.objects.filter(
                id__in=team_ids, tournament=tournament, status__in=["pending", "confirmed"]
            )
            valid_ids = list(registrations.values_list("id", flat=True))

            # Frontend sends the complete selection, so we replace the current selection
            if len(valid_ids) > selection_limit:
                return Response(
                    {"error": f"Cannot select more than {selection_limit} teams. " f"You selected: {len(valid_ids)}"},
                    status=400,
                )

            # Save the complete selection (replace existing)
            tournament.selected_teams[round_num] = valid_ids

        elif action == "eliminate":
            # Remove teams
            tournament.selected_teams[round_num] = [tid for tid in current_selected if tid not in team_ids]

        tournament.save(update_fields=["selected_teams"])
        cache.delete("tournaments:list:all")

        logger.info(
            f"Teams {action}ed - Tournament: {tournament.id}, Round: {round_num}, Count: {len(tournament.selected_teams[round_num])}"  # noqa E501
        )

        return Response(
            {
                "message": f"Teams {action}ed successfully",
                "selected_teams": tournament.selected_teams[round_num],
                "selected_count": len(tournament.selected_teams[round_num]),
            }
        )


class SubmitIGNView(APIView):
    """
    Captain submits IGNs for all team members.
    POST /api/tournaments/<tournament_id>/registrations/<registration_id>/submit-ign/
    Body: {"ign_submissions": {"username1": "IGN1", "username2": "IGN2", ...}}
    Can be re-submitted until tournament starts.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, tournament_id, registration_id):
        try:
            registration = TournamentRegistration.objects.select_related(
                "player__user", "tournament"
            ).get(id=registration_id, tournament_id=tournament_id)
        except TournamentRegistration.DoesNotExist:
            return Response({"error": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        # Only the captain can submit/edit IGNs
        if registration.player.user != request.user:
            return Response({"error": "Only the team captain can submit IGNs."}, status=status.HTTP_403_FORBIDDEN)

        tournament = registration.tournament

        # Block once tournament has started
        if tournament.status in ("ongoing", "completed"):
            return Response(
                {"error": "IGNs are locked once the tournament has started."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        incoming = request.data.get("ign_submissions")
        if not isinstance(incoming, dict) or not incoming:
            return Response({"error": "ign_submissions must be a non-empty object."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate each IGN value
        cleaned = {}
        for uname, ign_val in incoming.items():
            ign_clean = (ign_val or "").strip()
            if not ign_clean:
                return Response({"error": f"IGN for {uname} cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
            if len(ign_clean) > 50:
                return Response({"error": f"IGN for {uname} must be 50 characters or less."}, status=status.HTTP_400_BAD_REQUEST)
            cleaned[uname] = ign_clean

        # Merge with existing submissions (captain can update selectively)
        submissions = dict(registration.ign_submissions or {})
        submissions.update(cleaned)

        TournamentRegistration.objects.filter(pk=registration.pk).update(
            ign_submissions=submissions, ign_locked=True
        )
        registration.ign_submissions = submissions
        registration.ign_locked = True

        # Update each player's profile with their IGN (best-effort)
        game_name = tournament.game_name or tournament.game
        from accounts.models import User as _User
        for uname, ign_val in cleaned.items():
            try:
                u = _User.objects.filter(username=uname).select_related('player_profile').first()
                if u and hasattr(u, 'player_profile'):
                    gp = dict(u.player_profile.game_profiles or {})
                    gp[game_name] = {**gp.get(game_name, {}), "ign": ign_val}
                    u.player_profile.game_profiles = gp
                    u.player_profile.save(update_fields=["game_profiles"])
            except Exception:
                pass

        return Response(
            {
                "success": True,
                "ign_submissions": registration.ign_submissions,
                "ign_locked": registration.ign_locked,
            },
            status=status.HTTP_200_OK,
        )
