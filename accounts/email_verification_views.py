"""
Email Verification Views
Handles email verification for new users
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.tasks import send_verification_email_task

logger = logging.getLogger(__name__)


class SendVerificationEmailView(APIView):
    """
    Send/Resend email verification
    POST /api/accounts/send-verification-email/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        # Check if already verified
        if user.is_email_verified:
            return Response({"message": "Email is already verified"}, status=status.HTTP_200_OK)

        # Check if verification email was sent recently (prevent spam)
        if user.email_verification_sent_at:
            time_since_last_email = timezone.now() - user.email_verification_sent_at
            if time_since_last_email < timedelta(minutes=2):
                seconds_remaining = 120 - int(time_since_last_email.total_seconds())
                return Response(
                    {"error": f"Please wait {seconds_remaining} seconds before requesting another verification email"},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        # Generate new verification token
        verification_token = secrets.token_urlsafe(32)
        user.email_verification_token = verification_token
        user.email_verification_sent_at = timezone.now()
        user.save(update_fields=["email_verification_token", "email_verification_sent_at"])

        # Build verification URL
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        verification_url = f"{frontend_url}/verify-email/{verification_token}"

        # Send verification email asynchronously
        send_verification_email_task.delay(
            user_email=user.email, user_name=user.username, verification_url=verification_url
        )

        logger.info(f"Verification email sent to: {user.email}")

        return Response(
            {"message": "Verification email sent successfully", "email": user.email}, status=status.HTTP_200_OK
        )


class VerifyEmailView(APIView):
    """
    Verify email with token
    GET /api/accounts/verify-email/<token>/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            # Find user with this token
            user = User.objects.get(email_verification_token=token)

            # Check if already verified
            if user.is_email_verified:
                return Response({"message": "Email is already verified. You can login now."}, status=status.HTTP_200_OK)

            # Check if token is expired (24 hours)
            if user.email_verification_sent_at:
                time_since_sent = timezone.now() - user.email_verification_sent_at
                if time_since_sent > timedelta(hours=24):
                    return Response(
                        {
                            "error": "Verification link has expired",
                            "message": "Please register again or request a new verification email",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # ✅ ACTIVATE ACCOUNT
            user.is_email_verified = True
            user.is_active = True  # Activate the account
            user.email_verification_token = None  # Clear token after verification
            user.save(update_fields=["is_email_verified", "is_active", "email_verification_token"])

            # Send welcome email AFTER verification
            from django.conf import settings

            from accounts.tasks import send_welcome_email_task

            if user.user_type == "player":
                dashboard_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard"
            else:
                dashboard_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard"

            send_welcome_email_task.delay(
                user_email=user.email, user_name=user.username, dashboard_url=dashboard_url, user_type=user.user_type
            )

            logger.info(f"Email verified and account activated for user: {user.email}")

            return Response(
                {
                    "message": "Email verified successfully! Your account is now active. You can login now.",
                    "user": {
                        "email": user.email,
                        "username": user.username,
                        "is_email_verified": user.is_email_verified,
                        "is_active": user.is_active,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            logger.warning(f"Invalid verification token attempted: {token[:10]}...")
            return Response(
                {
                    "error": "Invalid verification link",
                    "message": "This verification link is invalid or has already been used",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Error during email verification: {str(e)}")
            return Response(
                {"error": "An error occurred during verification"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PublicResendVerificationEmailView(APIView):
    """
    Resend email verification for unauthenticated users
    POST /api/accounts/resend-verification/
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)

            # Check if already verified
            if user.is_email_verified:
                return Response({"message": "Email is already verified. You can login now."}, status=status.HTTP_200_OK)

            # Rate limiting check
            if user.email_verification_sent_at:
                time_since_last_email = timezone.now() - user.email_verification_sent_at
                if time_since_last_email < timedelta(minutes=2):
                    seconds_remaining = 120 - int(time_since_last_email.total_seconds())
                    return Response(
                        {
                            "error": (
                                f"Please wait {seconds_remaining} seconds before "
                                "requesting another verification email"
                            )
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

            # Generate new verification token
            verification_token = secrets.token_urlsafe(32)
            user.email_verification_token = verification_token
            user.email_verification_sent_at = timezone.now()
            user.save(update_fields=["email_verification_token", "email_verification_sent_at"])

            # Build verification URL
            frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
            verification_url = f"{frontend_url}/verify-email/{verification_token}"

            # Send verification email asynchronously
            send_verification_email_task.delay(
                user_email=user.email, user_name=user.username, verification_url=verification_url
            )

            logger.info(f"Public verification resend sent to: {user.email}")

            return Response(
                {"message": "Verification email resent successfully. Please check your inbox.", "email": email},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            # For security, don't reveal if user exists or not
            return Response(
                {"message": "If an account exists with this email, a verification link has been sent."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Error during public verification resend: {str(e)}")
            return Response(
                {"error": "An error occurred. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
