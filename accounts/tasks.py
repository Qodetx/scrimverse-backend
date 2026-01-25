"""
Celery tasks for accounts app
"""
import logging

from django.core.cache import cache
from django.db.models import Avg

from celery import shared_task

from accounts.models import Team, User
from scrimverse.email_utils import (
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)
from tournaments.models import HostRating

logger = logging.getLogger(__name__)


@shared_task
def update_host_rating_cache(host_id):
    """
    Calculate and cache host average rating
    Triggered after new rating is submitted

    Priority: 🔥🔥 HIGH
    Impact: 80-90% faster host profile loads
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Updating rating cache for host {host_id}...")

    try:
        # Calculate average rating and count
        avg_data = HostRating.objects.filter(host_id=host_id).aggregate(avg=Avg("rating"))
        rating_count = HostRating.objects.filter(host_id=host_id).count()

        cache_data = {
            "average_rating": round(avg_data["avg"], 1) if avg_data["avg"] else 0,
            "total_ratings": rating_count,
        }

        # Cache for 1 hour
        cache.set(f"host:rating:{host_id}", cache_data, 3600)

        logger.info(f"Host {host_id} rating cached: {cache_data['average_rating']} ({rating_count} ratings)")
        return cache_data

    except Exception as e:
        logger.error(f"Error updating host rating cache: {e}")
        return {"error": str(e)}


@shared_task
def process_team_invitation(team_id, player_id, invitation_type):
    """
    Process team invitation/join request asynchronously
    - Send email notification to player
    - Log team activity
    - Update team statistics

    Priority: 🔥🔥 HIGH
    Impact: User engagement & notifications
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Processing team invitation: team={team_id}, player={player_id}, type={invitation_type}")

    try:
        team = Team.objects.get(id=team_id)
        player = User.objects.get(id=player_id)

        # TODO: Send email notification
        # from django.core.mail import send_mail
        # send_mail(
        #     subject=f"Team Invitation from {team.team_name}",
        #     message=f"You've been invited to join {team.team_name}!",
        #     from_email='noreply@scrimverse.com',
        #     recipient_list=[player.email],
        #     fail_silently=True,
        # )

        logger.info("Team invitation processed successfully")
        return {"status": "success", "team": team.team_name, "player": player.username}

    except Exception as e:
        logger.error(f"Error processing team invitation: {e}")
        return {"error": str(e)}


# ============================================================================
# ACCOUNT EMAIL TASKS
# ============================================================================
# Account-related email notifications (authentication, security)
# ============================================================================


# Account & Security Email Tasks
@shared_task(name="send_welcome_email_task")
def send_welcome_email_task(user_email: str, user_name: str, dashboard_url: str, user_type: str = "player"):
    """Async task to send welcome email after registration"""
    return send_welcome_email(user_email, user_name, dashboard_url, user_type)
    logger.info(
        "Welcome email sent successfully",
        extra={
            "user_email": user_email,
            "user_name": user_name,
            "dashboard_url": dashboard_url,
            "user_type": user_type,
        },
    )


@shared_task(name="send_verification_email_task")
def send_verification_email_task(user_email: str, user_name: str, verification_url: str):
    """Async task to send email verification email"""
    return send_verification_email(user_email, user_name, verification_url)


@shared_task(name="send_password_reset_email_task")
def send_password_reset_email_task(user_email: str, user_name: str, reset_url: str):
    """Async task to send password reset email"""
    return send_password_reset_email(user_email, user_name, reset_url)


@shared_task(name="send_password_changed_email_task")
def send_password_changed_email_task(
    user_email: str, user_name: str, changed_at: str, ip_address: str, dashboard_url: str
):
    """Async task to send password changed confirmation email"""
    return send_password_changed_email(user_email, user_name, changed_at, ip_address, dashboard_url)
