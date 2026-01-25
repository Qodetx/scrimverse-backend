"""
Email utility functions for Scrimverse
Handles sending various types of emails using AWS SES
"""

import logging
from typing import Dict, List, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class EmailService:
    """Service class for sending emails"""

    @staticmethod
    def send_email(
        subject: str,
        template_name: str,
        context: Dict,
        recipient_list: List[str],
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Send an email using a template

        Args:
            subject: Email subject
            template_name: Name of the template file (without .html)
            context: Context dictionary for template rendering
            recipient_list: List of recipient email addresses
            from_email: Sender email (defaults to DEFAULT_FROM_EMAIL)

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Use default from email if not provided
            from_email = from_email or settings.DEFAULT_FROM_EMAIL

            # Render HTML content
            html_content = render_to_string(f"emails/{template_name}.html", context)

            # Create plain text version
            text_content = strip_tags(html_content)

            # Create email message
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=recipient_list,
            )

            # Attach HTML version
            email.attach_alternative(html_content, "text/html")

            # Send email
            email.send(fail_silently=False)

            logger.info(f"Email sent successfully: {subject} to {recipient_list}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {subject} to {recipient_list}. Error: {str(e)}")
            return False


# Account & Security Emails
def send_welcome_email(user_email: str, user_name: str, dashboard_url: str, user_type: str = "player") -> bool:
    """
    Send welcome email after successful registration

    Args:
        user_email: User's email address
        user_name: User's username
        dashboard_url: URL to user's dashboard
        user_type: Type of user - 'player' or 'host'
    """
    context = {
        "user_name": user_name,
        "dashboard_url": dashboard_url,
        "help_url": f"{settings.CORS_ALLOWED_ORIGINS[0]}/help",
        "user_type": user_type,  # Added user_type to context
    }
    return EmailService.send_email(
        subject="Welcome to Scrimverse! 🎮",
        template_name="welcome",
        context=context,
        recipient_list=[user_email],
    )


def send_verification_email(user_email: str, user_name: str, verification_url: str) -> bool:
    """
    Send email verification email

    Args:
        user_email: User's email address
        user_name: User's username
        verification_url: URL with verification token
    """
    context = {
        "user_name": user_name,
        "verification_url": verification_url,
    }
    return EmailService.send_email(
        subject="Verify Your Email - Scrimverse",
        template_name="verify_email",
        context=context,
        recipient_list=[user_email],
    )


def send_password_reset_email(user_email: str, user_name: str, reset_url: str) -> bool:
    """Send password reset email"""
    context = {
        "user_name": user_name,
        "reset_url": reset_url,
    }
    return EmailService.send_email(
        subject="Password Reset Request - Scrimverse",
        template_name="password_reset",
        context=context,
        recipient_list=[user_email],
    )


def send_password_changed_email(
    user_email: str, user_name: str, changed_at: str, ip_address: str, dashboard_url: str
) -> bool:
    """Send password changed confirmation email"""
    context = {
        "user_name": user_name,
        "changed_at": changed_at,
        "ip_address": ip_address,
        "dashboard_url": dashboard_url,
        "support_email": settings.SUPPORT_EMAIL,
    }
    return EmailService.send_email(
        subject="Password Changed Successfully - Scrimverse",
        template_name="password_changed",
        context=context,
        recipient_list=[user_email],
    )


# Tournament - Player Side Emails
def send_tournament_registration_email(
    user_email: str,
    user_name: str,
    tournament_name: str,
    game_name: str,
    start_date: str,
    registration_id: str,
    tournament_url: str,
    team_name: Optional[str] = None,
) -> bool:
    """Send tournament registration confirmation email"""
    context = {
        "user_name": user_name,
        "tournament_name": tournament_name,
        "game_name": game_name,
        "start_date": start_date,
        "registration_id": registration_id,
        "tournament_url": tournament_url,
        "team_name": team_name,
    }
    return EmailService.send_email(
        subject=f"Registration Confirmed - {tournament_name}",
        template_name="tournament_registration",
        context=context,
        recipient_list=[user_email],
    )


def send_tournament_results_email(
    user_email: str,
    user_name: str,
    tournament_name: str,
    position: int,
    total_participants: int,
    results_url: str,
    team_name: Optional[str] = None,
) -> bool:
    """Send tournament results email"""
    context = {
        "user_name": user_name,
        "tournament_name": tournament_name,
        "position": position,
        "total_participants": total_participants,
        "results_url": results_url,
        "team_name": team_name,
    }
    return EmailService.send_email(
        subject=f"Results Published - {tournament_name}",
        template_name="tournament_results",
        context=context,
        recipient_list=[user_email],
    )


def send_premium_tournament_promo_email(
    user_email: str,
    user_name: str,
    tournament_name: str,
    game_name: str,
    prize_pool: str,
    registration_deadline: str,
    start_date: str,
    tournament_url: str,
) -> bool:
    """Send premium tournament promotion email"""
    context = {
        "user_name": user_name,
        "tournament_name": tournament_name,
        "game_name": game_name,
        "prize_pool": prize_pool,
        "registration_deadline": registration_deadline,
        "start_date": start_date,
        "tournament_url": tournament_url,
    }
    return EmailService.send_email(
        subject=f"Premium Tournament Alert - {tournament_name}",
        template_name="premium_tournament_promo",
        context=context,
        recipient_list=[user_email],
    )


# Tournament - Host Side Emails
def send_host_approved_email(
    user_email: str, user_name: str, host_name: str, approved_at: str, host_dashboard_url: str
) -> bool:
    """Send host account approval email"""
    context = {
        "user_name": user_name,
        "host_name": host_name,
        "approved_at": approved_at,
        "host_dashboard_url": host_dashboard_url,
        "guide_url": f"{settings.CORS_ALLOWED_ORIGINS[0]}/host-guide",
    }
    return EmailService.send_email(
        subject="Host Account Approved - Scrimverse",
        template_name="host_approved",
        context=context,
        recipient_list=[user_email],
    )


def send_tournament_created_email(
    host_email: str,
    host_name: str,
    tournament_name: str,
    game_name: str,
    start_date: str,
    max_participants: int,
    plan_type: str,
    tournament_url: str,
    tournament_manage_url: str,
) -> bool:
    """Send tournament created confirmation email"""
    context = {
        "host_name": host_name,
        "tournament_name": tournament_name,
        "game_name": game_name,
        "start_date": start_date,
        "max_participants": max_participants,
        "plan_type": plan_type,
        "tournament_url": tournament_url,
        "tournament_manage_url": tournament_manage_url,
    }
    return EmailService.send_email(
        subject=f"Tournament Created - {tournament_name}",
        template_name="tournament_created",
        context=context,
        recipient_list=[host_email],
    )


def send_tournament_reminder_email(
    host_email: str,
    host_name: str,
    tournament_name: str,
    start_time: str,
    total_registrations: int,
    tournament_manage_url: str,
) -> bool:
    """Send tournament reminder email (same day)"""
    context = {
        "host_name": host_name,
        "tournament_name": tournament_name,
        "start_time": start_time,
        "total_registrations": total_registrations,
        "tournament_manage_url": tournament_manage_url,
    }
    return EmailService.send_email(
        subject=f"Tournament Starting Today - {tournament_name}",
        template_name="tournament_reminder",
        context=context,
        recipient_list=[host_email],
    )


def send_registration_limit_reached_email(
    host_email: str,
    host_name: str,
    tournament_name: str,
    total_registrations: int,
    max_participants: int,
    start_date: str,
    tournament_manage_url: str,
) -> bool:
    """Send email when tournament registration limit is reached"""
    context = {
        "host_name": host_name,
        "tournament_name": tournament_name,
        "total_registrations": total_registrations,
        "max_participants": max_participants,
        "start_date": start_date,
        "tournament_manage_url": tournament_manage_url,
    }
    return EmailService.send_email(
        subject=f"Registration Full - {tournament_name}",
        template_name="registration_limit_reached",
        context=context,
        recipient_list=[host_email],
    )


def send_tournament_completed_email(
    host_email: str,
    host_name: str,
    tournament_name: str,
    completed_at: str,
    total_participants: int,
    total_matches: int,
    winner_name: str,
    runner_up_name: str,
    total_registrations: int,
    results_published: bool,
    tournament_manage_url: str,
) -> bool:
    """Send tournament completion summary email"""
    context = {
        "host_name": host_name,
        "tournament_name": tournament_name,
        "completed_at": completed_at,
        "total_participants": total_participants,
        "total_matches": total_matches,
        "winner_name": winner_name,
        "runner_up_name": runner_up_name,
        "total_registrations": total_registrations,
        "results_published": results_published,
        "tournament_manage_url": tournament_manage_url,
    }
    return EmailService.send_email(
        subject=f"Tournament Completed - {tournament_name}",
        template_name="tournament_completed",
        context=context,
        recipient_list=[host_email],
    )
