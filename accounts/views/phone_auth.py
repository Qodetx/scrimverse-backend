"""
Phone-based authentication views.
Supports OTP login for existing users and phone-only signup for new users.
Phone-registered accounts skip email verification — the phone OTP IS their verification.
"""
import logging
import random

from django.contrib.auth.models import update_last_login
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import PlayerProfile, User
from accounts.serializers.user import UserSerializer
from scrimverse.sms_utils import send_otp_sms

logger = logging.getLogger("accounts")

OTP_TTL = 600        # 10 minutes
OTP_RATE_LIMIT = 3   # max sends per window
OTP_RATE_TTL = 600   # rate-limit window (seconds)


def _normalize_phone(phone):
    """Strip non-digits and normalize to 10-digit Indian number."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


def _phone_auth_otp_key(phone):
    return f"otp:phone_auth:{phone}"


def _phone_auth_rate_key(phone):
    return f"otp_rate:phone_auth:{phone}"


def _generate_otp():
    return str(random.randint(100000, 999999))


def _build_jwt_response(user, message, http_status=status.HTTP_200_OK):
    """Generate JWT tokens and build the standard auth response."""
    refresh = RefreshToken.for_user(user)
    update_last_login(None, user)
    data = {
        "user": UserSerializer(user).data,
        "tokens": {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        },
        "message": message,
    }
    return Response(data, status=http_status)


class SendPhoneAuthOTPView(APIView):
    """
    POST /api/accounts/send-phone-auth-otp/
    Body: { "phone_number": "9876543210" }

    Works for both login (existing user) and signup (new user).
    Returns is_new_user so the frontend can show/hide the username field.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone_number", "").strip()
        if not phone:
            return Response({"error": "phone_number is required"}, status=status.HTTP_400_BAD_REQUEST)

        digits = _normalize_phone(phone)
        if len(digits) != 10:
            return Response(
                {"error": "Enter a valid 10-digit Indian mobile number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rate limiting keyed on phone number
        rate_key = _phone_auth_rate_key(digits)
        count = cache.get(rate_key, 0)
        if count >= OTP_RATE_LIMIT:
            return Response(
                {"error": "Too many OTP requests. Please wait 10 minutes before trying again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Determine new vs existing user
        is_new_user = not User.objects.filter(phone_number=digits, is_active=True).exists()

        # Generate and store OTP in Redis
        otp = _generate_otp()
        cache.set(_phone_auth_otp_key(digits), otp, timeout=OTP_TTL)

        # Increment rate counter
        if count == 0:
            cache.set(rate_key, 1, timeout=OTP_RATE_TTL)
        else:
            cache.incr(rate_key)

        send_otp_sms(digits, otp)
        logger.info(f"Phone auth OTP sent - Phone: {digits[:5]}***** is_new_user={is_new_user}")

        return Response(
            {"message": "OTP sent successfully", "is_new_user": is_new_user, "expires_in": OTP_TTL},
            status=status.HTTP_200_OK,
        )


class PhoneLoginView(APIView):
    """
    POST /api/accounts/phone-login/
    Body: { "phone_number": "9876543210", "otp": "123456" }

    Verifies OTP for an existing user and returns JWT tokens.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone_number", "").strip()
        otp_input = request.data.get("otp", "").strip()

        if not phone or not otp_input:
            return Response(
                {"error": "phone_number and otp are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        digits = _normalize_phone(phone)
        if len(digits) != 10:
            return Response(
                {"error": "Enter a valid 10-digit Indian mobile number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find user by phone number
        try:
            user = User.objects.get(phone_number=digits, is_active=True)
        except User.DoesNotExist:
            return Response(
                {"error": "No account found with this phone number."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verify OTP
        otp_key = _phone_auth_otp_key(digits)
        stored_otp = cache.get(otp_key)
        if not stored_otp or stored_otp != otp_input:
            return Response(
                {"error": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # One-time use — delete immediately after verification
        cache.delete(otp_key)

        logger.info(f"Phone login successful - User ID: {user.id}, Username: {user.username}")
        return _build_jwt_response(user, "Login successful!")


class PhoneRegisterView(APIView):
    """
    POST /api/accounts/phone-register/
    Body: { "phone_number": "9876543210", "otp": "123456", "username": "gamertag" }

    Creates a new player account with phone as primary identifier.
    No email verification required — phone OTP is the verification.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone_number", "").strip()
        otp_input = request.data.get("otp", "").strip()
        username = request.data.get("username", "").strip()

        if not phone or not otp_input or not username:
            return Response(
                {"error": "phone_number, otp, and username are all required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        digits = _normalize_phone(phone)
        if len(digits) != 10:
            return Response(
                {"error": "Enter a valid 10-digit Indian mobile number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Username validation
        if len(username) < 3:
            return Response(
                {"error": "Username must be at least 3 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not all(c.isalnum() or c in ("_", "-") for c in username):
            return Response(
                {"error": "Username can only contain letters, numbers, _ and -."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username__iexact=username).exists():
            return Response(
                {"error": "This username is already taken. Please choose another."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard: phone already registered
        if User.objects.filter(phone_number=digits, is_active=True).exists():
            return Response(
                {"error": "An account with this phone number already exists. Please login instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify OTP (must come after all other validations so OTP isn't wasted on bad input)
        otp_key = _phone_auth_otp_key(digits)
        stored_otp = cache.get(otp_key)
        if not stored_otp or stored_otp != otp_input:
            return Response(
                {"error": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cache.delete(otp_key)

        # Create user — phone-only accounts use a placeholder email
        # (phone_XXXXXXXXXX@scrimverse.internal, unique, never shown to user)
        placeholder_email = f"phone_{digits}@scrimverse.internal"
        user = User(
            email=placeholder_email,
            username=username,
            user_type="player",
            phone_number=digits,
            is_phone_verified=True,
            is_email_verified=True,  # phone OTP IS the verification
            is_active=True,
        )
        user.set_unusable_password()
        user.save()

        # Create empty PlayerProfile
        PlayerProfile.objects.create(user=user)

        logger.info(f"Phone registration successful - User ID: {user.id}, Username: {username}")
        return _build_jwt_response(user, "Account created successfully!", http_status=status.HTTP_201_CREATED)
