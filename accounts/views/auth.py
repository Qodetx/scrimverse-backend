import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.google_auth import GoogleOAuth
from accounts.models import HostProfile, PlayerProfile, User
from accounts.serializers import (
    HostProfileSerializer,
    HostRegistrationSerializer,
    LoginSerializer,
    PlayerProfileSerializer,
    PlayerRegistrationSerializer,
    UserSerializer,
)
from accounts.tasks import send_verification_email_task, send_welcome_email_task

logger = logging.getLogger(__name__)


class PlayerRegistrationView(generics.CreateAPIView):
    """
    Player Registration API
    POST /api/accounts/player/register/
    """

    serializer_class = PlayerRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        email = request.data.get("email")
        phone_number = request.data.get("phone_number", "").strip()
        otp_verified_token = request.data.get("otp_verified_token", "").strip()
        msg91_access_token = request.data.get("msg91_access_token", "").strip()
        next_url = request.data.get("next", "").strip() or None

        # Validate phone OTP verification — accept either legacy Redis token or MSG91 access token
        if phone_number:
            digits = "".join(c for c in phone_number if c.isdigit())
            if digits.startswith("91") and len(digits) == 12:
                digits = digits[2:]
            if digits.startswith("0") and len(digits) == 11:
                digits = digits[1:]

            if msg91_access_token:
                # MSG91 widget verification
                from accounts.views.otp_views import verify_msg91_access_token
                ok, result = verify_msg91_access_token(msg91_access_token)
                if not ok:
                    return Response(
                        {"error": f"Phone verification failed: {result}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif otp_verified_token:
                # Legacy Redis OTP verification
                from django.core.cache import cache
                verified_key = f"otp_verified:reg:{digits}"
                stored_token = cache.get(verified_key)
                if not stored_token or stored_token != otp_verified_token:
                    return Response(
                        {"error": "Phone verification expired or invalid. Please verify your phone again."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    {"error": "Phone number must be verified via OTP before registration."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if user already exists with this email
        if email:
            try:
                existing_user = User.objects.get(email=email)

                # If user exists but is NOT verified, delete the old account and allow re-registration
                if not existing_user.is_email_verified:
                    logger.info(
                        f"Deleting unverified account for {email} to allow re-registration (user_type: {existing_user.user_type})"  # noqa: E501
                    )
                    existing_user.delete()
                    # Continue with registration below
                else:
                    # User exists and is verified - return error
                    return Response(
                        {
                            "error": "An account with this email already exists and is verified. Please login instead.",
                            "email": email,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except User.DoesNotExist:
                # User doesn't exist, continue with registration
                pass

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # Return validation errors without consuming the OTP token
            # Flatten errors so the frontend gets a readable message
            errors = serializer.errors
            flat_errors = []
            for field, msgs in errors.items():
                for msg in msgs:
                    flat_errors.append(str(msg))
            return Response(
                {"error": "; ".join(flat_errors), "field_errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = serializer.save()

        # Store post-verify redirect URL if provided
        if next_url:
            user.post_verify_redirect = next_url
            user.save(update_fields=["post_verify_redirect"])

        # Consume legacy Redis token after successful registration (one-time use)
        if phone_number and otp_verified_token:
            from django.core.cache import cache as _cache
            _digits = "".join(c for c in phone_number if c.isdigit())
            if _digits.startswith("91") and len(_digits) == 12:
                _digits = _digits[2:]
            if _digits.startswith("0") and len(_digits) == 11:
                _digits = _digits[1:]
            _cache.delete(f"otp_verified:reg:{_digits}")

        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        user.email_verification_token = verification_token
        user.email_verification_sent_at = timezone.now()
        user.is_email_verified = False
        user.is_active = False

        # Mark phone as verified if OTP was verified (either method)
        if phone_number and (otp_verified_token or msg91_access_token):
            user.is_phone_verified = True

        user.save(
            update_fields=["email_verification_token", "email_verification_sent_at", "is_email_verified", "is_active", "is_phone_verified"]
        )

        # Send verification email (NOT welcome email)
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        verification_url = f"{frontend_url}/verify-email/{verification_token}"

        send_verification_email_task.delay(
            user_email=user.email, user_name=user.username, verification_url=verification_url
        )
        logger.info(f"Verification email sent to player: {user.email}")

        # DO NOT return tokens - user must verify email first
        return Response(
            {
                "message": "Registration successful! Please check your email to verify your account.",
                "email": user.email,
                "verification_required": True,
            },
            status=status.HTTP_201_CREATED,
        )


class HostRegistrationView(generics.CreateAPIView):
    """
    Host Registration API
    POST /api/accounts/host/register/
    """

    serializer_class = HostRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        email = request.data.get("email")

        # Check if user already exists with this email
        if email:
            try:
                existing_user = User.objects.get(email=email)

                # If user exists but is NOT verified, delete the old account and allow re-registration
                if not existing_user.is_email_verified:
                    logger.info(
                        f"Deleting unverified account for {email} to allow re-registration (user_type: {existing_user.user_type})"  # noqa: E501
                    )
                    existing_user.delete()
                    # Continue with registration below
                else:
                    # User exists and is verified - return error
                    return Response(
                        {
                            "error": "An account with this email already exists and is verified. Please login instead.",
                            "email": email,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except User.DoesNotExist:
                # User doesn't exist, continue with registration
                pass

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        user.email_verification_token = verification_token
        user.email_verification_sent_at = timezone.now()
        user.is_email_verified = False  # Explicitly set to False
        user.is_active = False  # Deactivate account until email is verified
        user.save(
            update_fields=["email_verification_token", "email_verification_sent_at", "is_email_verified", "is_active"]
        )

        # Send verification email (NOT welcome email)
        frontend_url = settings.CORS_ALLOWED_ORIGINS[0]
        verification_url = f"{frontend_url}/verify-email/{verification_token}"

        send_verification_email_task.delay(
            user_email=user.email, user_name=user.username, verification_url=verification_url
        )
        logger.info(f"Verification email sent to host: {user.email}")

        # DO NOT return tokens - user must verify email first
        return Response(
            {
                "message": "Registration successful! Please check your email to verify your account.",
                "email": user.email,
                "verification_required": True,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    Login API for both Players and Hosts
    POST /api/accounts/login/
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        logger = logging.getLogger("accounts")

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user_type = serializer.validated_data["user_type"]

        logger.info(f"Login attempt - Email: {email}, User Type: {user_type}")

        # Check if user exists
        try:
            user_obj = User.objects.get(email=email)
            logger.debug(f"User found - ID: {user_obj.id}, Username: {user_obj.username}, Type: {user_obj.user_type}")
        except User.DoesNotExist:
            logger.warning(f"Login failed - No account found for email: {email}")
            return Response({"error": "No account found with this email address"}, status=status.HTTP_401_UNAUTHORIZED)

        # Authenticate user
        user = authenticate(request, username=email, password=password)

        if user is None:
            # Check if login failed because account is inactive
            if user_obj and not user_obj.is_active:
                logger.warning(f"Login failed - Account inactive/unverified for email: {email}")
                return Response(
                    {
                        "error": (
                            "Please verify your email address before logging in. "
                            "Check your inbox for the verification link."
                        )
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            logger.warning(f"Login failed - Incorrect password for email: {email}")
            return Response({"error": "Incorrect password. Please try again."}, status=status.HTTP_401_UNAUTHORIZED)

        # Check user type matches
        if user.user_type != user_type:
            logger.warning(
                f"Login failed - User type mismatch. Expected: {user_type}, Actual: {user.user_type} for email: {email}"
            )
            return Response(
                {"error": f"This account is not registered as a {user_type}"}, status=status.HTTP_403_FORBIDDEN
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # Update last_login timestamp (required for new user indicator)
        from django.contrib.auth.models import update_last_login
        update_last_login(None, user)

        logger.info(f"Login successful - User ID: {user.id}, Username: {user.username}, Type: {user.user_type}")

        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "message": "Login successful!",
            },
            status=status.HTTP_200_OK,
        )


class GoogleAuthView(APIView):
    """
    Google OAuth Authentication for Player and Host
    POST /api/accounts/google-auth/

    Request body:
    {
        "token": "google_oauth_token",
        "user_type": "player" or "host"
    }
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get("token")
        user_type = request.data.get("user_type")
        username = request.data.get("username")  # Required for signup
        phone_number = request.data.get("phone_number")  # Required for signup
        is_signup = request.data.get("is_signup", False)  # Flag to distinguish login vs signup

        if not token:
            return Response({"error": "Google token is required"}, status=status.HTTP_400_BAD_REQUEST)

        if user_type not in ["player", "host"]:
            return Response({"error": "user_type must be 'player' or 'host'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Verify Google token and get user info
            google_user_info = GoogleOAuth.verify_google_token(token)

            if not google_user_info.get("email_verified"):
                return Response({"error": "Google email not verified"}, status=status.HTTP_400_BAD_REQUEST)

            email = google_user_info["email"]

            # Check if user already exists
            try:
                user = User.objects.get(email=email)

                # Check if user type matches
                if user.user_type != user_type:
                    return Response(
                        {"error": f"This email is already registered as a {user.user_type}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # User exists, log them in
                message = "Login successful!"

            except User.DoesNotExist:
                # User doesn't exist — auto-create and log them in.
                # Google has already verified the email so there is no reason
                # to reject a new user based on whether they clicked Login vs
                # Sign Up. Both flows result in the same outcome.

                # Auto-generate username
                raw_username = username or google_user_info.get("given_name") or email.split("@")[0]
                # sanitize: keep alphanumerics and underscore
                base = re.sub(r"[^0-9a-zA-Z_]", "", raw_username)[:24] or "player"
                candidate = base
                suffix = 0
                while User.objects.filter(username=candidate).exists():
                    suffix += 1
                    candidate = f"{base}{suffix}"

                final_username = candidate
                phone_value = phone_number or ""

                # Create user without password (Google OAuth users)
                user = User.objects.create(
                    email=email,
                    username=final_username,
                    user_type=user_type,
                    phone_number=phone_value,
                    is_email_verified=True,  # Google already verified email
                    is_active=True,  # Activate account immediately
                )

                # Set unusable password for OAuth users
                user.set_unusable_password()
                user.save()

                # Create corresponding profile
                if user_type == "player":
                    PlayerProfile.objects.create(user=user)
                else:
                    HostProfile.objects.create(user=user)

                # Send welcome email asynchronously
                if user_type == "player":
                    dashboard_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/player/dashboard"
                else:
                    dashboard_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard"

                send_welcome_email_task.delay(
                    user_email=user.email, user_name=user.username, dashboard_url=dashboard_url, user_type=user_type
                )
                logger.info(f"Welcome email queued for Google OAuth {user_type}: {user.email}")

                message = "Account created successfully!"
                logger.debug(f"Google OAuth account created - ID: {user.id}, Username: {username}, Type: {user_type}")

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            # Update last_login timestamp (required for new user indicator)
            from django.contrib.auth.models import update_last_login
            update_last_login(None, user)

            # Get profile data
            if user_type == "player":
                profile = PlayerProfile.objects.get(user=user)
                profile_data = PlayerProfileSerializer(profile).data
            else:
                profile = HostProfile.objects.get(user=user)
                profile_data = HostProfileSerializer(profile).data

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "profile": profile_data,
                    "tokens": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    },
                    "message": message,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Authentication failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurrentUserView(APIView):
    """
    Get and Update current logged-in user details
    GET/PATCH /api/accounts/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        # Get game filter from query params (default: 'ALL')
        game_filter = request.query_params.get('game', 'ALL')

        serializer = UserSerializer(user, context={"request": request})

        profile_data = None
        if user.user_type == "player" and hasattr(user, "player_profile"):
            profile_data = PlayerProfileSerializer(
                user.player_profile,
                context={"request": request, "game_filter": game_filter}
            ).data
        elif user.user_type == "host" and hasattr(user, "host_profile"):
            profile_data = HostProfileSerializer(user.host_profile, context={"request": request}).data

        return Response({"user": serializer.data, "profile": profile_data}, status=status.HTTP_200_OK)

    def patch(self, request):
        user = request.user
        data = request.data.copy()

        # Email cannot be changed
        if "email" in data:
            del data["email"]

        # Username change restriction logic
        new_username = data.get("username")
        if new_username and new_username != user.username:
            # If they have already changed it once
            if user.username_change_count > 0:
                # Check if 6 months (approx 180 days) have passed
                if user.last_username_change:
                    six_months_ago = timezone.now() - timedelta(days=180)
                    if user.last_username_change > six_months_ago:
                        days_left = (user.last_username_change + timedelta(days=180) - timezone.now()).days
                        return Response(
                            {
                                "error": (
                                    f"Username can only be changed once every 6 months. "
                                    f"Please try again in {days_left} days."
                                )
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            # Increment change count and update timestamp
            user.username_change_count += 1
            user.last_username_change = timezone.now()
            user.save()

        # Update user fields
        serializer = UserSerializer(user, data=data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    Change password for authenticated user
    POST /api/accounts/change-password/
    Body: { current_password, new_password }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")
        otp_input = request.data.get("otp", "")

        if not current_password or not new_password or not otp_input:
            return Response(
                {"error": "current_password, new_password, and otp are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"error": "New password must be at least 8 characters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(current_password):
            return Response({"error": "Current password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify OTP (Redis-based, one-time use)
        from accounts.views.otp_views import verify_otp
        if not verify_otp("password_change", user.id, otp_input):
            return Response(
                {"error": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save()
        logger.info(f"Password changed - User: {user.id}")
        return Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)
