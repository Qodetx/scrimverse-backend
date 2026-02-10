"""
Service layer for Invite-Based Tournament Registration.

Handles the post-payment logic:
1. Mark registration as paid + confirmed.
2. Create a real Team object.
3. Create TeamJoinRequest invite records for each teammate email.
4. Queue async invite emails.
"""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Team, TeamJoinRequest, TeamMember

logger = logging.getLogger(__name__)


def process_successful_registration(registration, merchant_order_id):
    """
    Called after payment is confirmed for an invite-based registration.

    Args:
        registration: TournamentRegistration instance (already has temp_teammate_emails, team_name, etc.)
        merchant_order_id: The payment order ID to store on the registration.

    Returns:
        dict with keys: team, invites (list of TeamJoinRequest objects)
    """
    with transaction.atomic():
        # ----------------------------------------------------------------
        # 1. Update registration status
        # ----------------------------------------------------------------
        registration.payment_status = True
        registration.payment_id = merchant_order_id
        registration.status = "confirmed"
        registration.save(update_fields=["payment_status", "payment_id", "status", "updated_at"])

        logger.info(
            f"Registration {registration.id} confirmed (payment={merchant_order_id})"
        )

        # ----------------------------------------------------------------
        # 2. Create a real Team object
        # ----------------------------------------------------------------
        team_name = registration.team_name or f"Team-{registration.id}"

        # Handle possible team-name collision (unlikely but safe)
        base_name = team_name
        attempt = 0
        while Team.objects.filter(name=team_name, captain=registration.player.user).exists():
            attempt += 1
            team_name = f"{base_name}-{uuid.uuid4().hex[:4]}"
            if attempt > 5:
                break  # safety valve

        team = Team.objects.create(
            name=team_name,
            captain=registration.player.user,
            is_temporary=False,
        )

        # Add captain as a team member
        TeamMember.objects.create(
            team=team,
            user=registration.player.user,
            username=registration.player.user.username,
            is_captain=True,
        )

        # Link team to registration
        registration.team = team
        registration.is_team_created = True
        registration.save(update_fields=["team", "is_team_created", "updated_at"])

        logger.info(f"Team '{team.name}' (id={team.id}) created for registration {registration.id}")

        # ----------------------------------------------------------------
        # 3. Create TeamJoinRequest invite records
        # ----------------------------------------------------------------
        teammate_emails = registration.temp_teammate_emails or []
        invites = []

        for email in teammate_emails:
            email_lower = email.lower().strip()
            if not email_lower:
                continue

            invite_token = uuid.uuid4().hex  # 32-char hex token
            invite = TeamJoinRequest.objects.create(
                team=team,
                player=None,  # will be filled when invitee accepts
                request_type="invite",
                status="pending",
                invite_token=invite_token,
                invited_email=email_lower,
                invite_expires_at=timezone.now() + timedelta(days=7),
                tournament_registration=registration,
            )
            invites.append(invite)

        logger.info(f"{len(invites)} invite(s) created for registration {registration.id}")

        # ----------------------------------------------------------------
        # 4. Initialize invited_members_status on registration
        # ----------------------------------------------------------------
        invited_status = {
            inv.invited_email: {"status": "pending", "username": None}
            for inv in invites
        }
        registration.invited_members_status = invited_status
        registration.save(update_fields=["invited_members_status", "updated_at"])

        # ----------------------------------------------------------------
        # 5. Update tournament participant count
        # ----------------------------------------------------------------
        tournament = registration.tournament
        tournament.current_participants += 1
        tournament.save(update_fields=["current_participants", "updated_at"])

        # ----------------------------------------------------------------
        # 6. Queue invite emails (Celery tasks)
        # ----------------------------------------------------------------
        from tournaments.tasks import send_team_invite_emails_task

        send_team_invite_emails_task.delay(registration.id)

        logger.info(f"Invite email task queued for registration {registration.id}")

        return {"team": team, "invites": invites}
