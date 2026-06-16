import logging
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from scrimverse.email_utils import EmailService

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task(bind=True, max_retries=1)
def send_broadcast_email_task(self, broadcast_id):
    """
    Celery task to send a broadcast email to the resolved recipient list.

    Recipient resolution:
      - all_users: every verified User (player + host)
      - all_players: verified users with user_type='player'
      - all_hosts: verified users with user_type='host'
      - tournament_participants: confirmed TournamentRegistration players for
            selected tournaments (or all tournaments filtered by status)
      - individual_users: hand-picked users from selected_users M2M
    """
    from communications.models import BroadcastEmail
    from tournaments.models import TournamentRegistration, Tournament

    try:
        broadcast = BroadcastEmail.objects.get(pk=broadcast_id)
    except BroadcastEmail.DoesNotExist:
        logger.error(f"BroadcastEmail id={broadcast_id} not found.")
        return

    # Mark as sending
    broadcast.status = "sending"
    broadcast.save(update_fields=["status"])

    try:
        emails = _resolve_recipients(broadcast, TournamentRegistration, Tournament)

        if not emails:
            broadcast.status = "failed"
            broadcast.error_message = "No recipients found for the selected criteria."
            broadcast.save(update_fields=["status", "error_message"])
            logger.warning(f"Broadcast id={broadcast_id}: no recipients resolved.")
            return

        sent_count = 0
        failed_count = 0

        # Split body into lines for template rendering (preserves blank lines as <br>)
        body_lines = broadcast.body.splitlines()

        for email in emails:
            try:
                success = EmailService.send_email(
                    subject=broadcast.subject,
                    template_name="broadcast",
                    context={
                        "subject": broadcast.subject,
                        "body_lines": body_lines,
                    },
                    recipient_list=[email],
                )
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                    logger.error(f"EmailService returned False for broadcast to {email}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to send broadcast to {email}: {e}")

        broadcast.status = "sent" if failed_count == 0 else ("failed" if sent_count == 0 else "sent")
        broadcast.total_sent = sent_count
        broadcast.sent_at = timezone.now()
        if failed_count > 0:
            broadcast.error_message = f"{failed_count} email(s) failed to send out of {len(emails)} total."
        broadcast.save(update_fields=["status", "total_sent", "sent_at", "error_message"])

        logger.info(
            f"Broadcast id={broadcast_id} complete: {sent_count} sent, {failed_count} failed."
        )

    except Exception as e:
        broadcast.status = "failed"
        broadcast.error_message = str(e)
        broadcast.save(update_fields=["status", "error_message"])
        logger.error(f"Broadcast id={broadcast_id} task error: {e}")
        raise


def _resolve_recipients(broadcast, TournamentRegistration, Tournament):
    """
    Returns a deduplicated list of email addresses based on recipient_type.
    Only includes users with is_email_verified=True.
    """
    rtype = broadcast.recipient_type

    if rtype == "all_users":
        qs = User.objects.filter(is_email_verified=True, is_active=True)
        return list(qs.values_list("email", flat=True).distinct())

    elif rtype == "all_players":
        qs = User.objects.filter(
            user_type="player", is_email_verified=True, is_active=True
        )
        return list(qs.values_list("email", flat=True).distinct())

    elif rtype == "all_hosts":
        qs = User.objects.filter(
            user_type="host", is_email_verified=True, is_active=True
        )
        return list(qs.values_list("email", flat=True).distinct())

    elif rtype == "individual_users":
        qs = broadcast.selected_users.filter(is_email_verified=True, is_active=True)
        return list(qs.values_list("email", flat=True).distinct())

    elif rtype == "tournament_participants":
        # Build tournament queryset
        selected = broadcast.selected_tournaments.all()
        if selected.exists():
            tournament_qs = selected
        else:
            # No specific tournaments selected — use all, filtered by status
            status_filter = broadcast.tournament_status_filter
            if status_filter == "all":
                tournament_qs = Tournament.objects.all()
            else:
                status_map = {
                    "upcoming": "upcoming",
                    "ongoing": "ongoing",
                    "completed": "completed",
                }
                tournament_qs = Tournament.objects.filter(
                    status=status_map.get(status_filter, "upcoming")
                )

        # --- registration status filter ---
        reg_status = getattr(broadcast, "registration_status_filter", "confirmed")
        if reg_status == "all":
            status_filter_kwargs = {}
        else:
            status_filter_kwargs = {"status": reg_status}

        registrations = TournamentRegistration.objects.filter(
            tournament__in=tournament_qs,
            **status_filter_kwargs,
        ).select_related("player__user")

        # --- group filter (round + group) ---
        selected_groups = broadcast.selected_groups.all()
        if selected_groups.exists():
            registrations = registrations.filter(
                tournament_groups__in=selected_groups
            ).distinct()

        # --- IGN filter ---
        ign_filter = getattr(broadcast, "ign_filter", "all")
        if ign_filter == "submitted":
            # ign_submissions is a JSONField; non-empty means they submitted
            registrations = registrations.exclude(ign_submissions={})
        elif ign_filter == "not_submitted":
            registrations = registrations.filter(ign_submissions={})

        emails = set()
        for reg in registrations:
            try:
                user = reg.player.user
                if user.is_email_verified and user.is_active:
                    emails.add(user.email)
            except Exception:
                pass
        return list(emails)

    return []
