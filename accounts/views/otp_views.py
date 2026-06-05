"""
OTP Verification views for phone number change and password change.
OTPs are stored in Redis (NOT database) with auto-expiry for security and performance.

Redis key scheme:
  otp:{purpose}:{user_id}     -> 6-digit OTP code, TTL 600s
  otp_rate:{user_id}          -> send count, TTL 600s (max 3 per 10 min)
"""
import logging
import random
import uuid

from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from scrimverse.sms_utils import send_otp_sms

logger = logging.getLogger("accounts")

OTP_TTL = 600          # 10 minutes
OTP_RATE_LIMIT = 3     # max sends per window
OTP_RATE_TTL = 600     # rate limit window (10 min)
REG_OTP_VERIFIED_TTL = 900  # 15 minutes for registration token validity
VALID_PURPOSES = {"phone_change", "password_change"}


def _generate_otp():
    return str(random.randint(100000, 999999))


def _otp_key(purpose, user_id):
    return f"otp:{purpose}:{user_id}"


def _rate_key(user_id):
    return f"otp_rate:{user_id}"


def verify_otp(purpose, user_id, otp_input):
    """
    Verify an OTP and delete it on success (one-time use).
    Returns True if valid, False otherwise.
    """
    key = _otp_key(purpose, user_id)
    stored = cache.get(key)
    if not stored or stored != str(otp_input).strip():
        return False
    cache.delete(key)  # One-time use — delete after successful verify
    return True


class SendOTPView(APIView):
    """
    POST /api/accounts/send-otp/
    Body: { "purpose": "phone_change" | "password_change", "phone": "9876543210" }
    Generates a 6-digit OTP, stores in Redis, sends via SMS.
    Rate limited: max 3 sends per 10 minutes per user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        purpose = request.data.get("purpose", "").strip()
        phone = request.data.get("phone", "").strip()

        if purpose not in VALID_PURPOSES:
            return Response(
                {"error": f"Invalid purpose. Must be one of: {', '.join(VALID_PURPOSES)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not phone:
            return Response({"error": "phone is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize phone: strip non-digits, strip +91 prefix
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) != 10:
            return Response(
                {"error": "Phone must be a valid 10-digit Indian mobile number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Block if phone is already verified on another account
        if purpose == 'phone_change':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            if User.objects.filter(phone_number=digits, is_phone_verified=True).exclude(pk=request.user.pk).exists():
                return Response(
                    {"error": "This phone number is already registered to another account."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Rate limiting
        rate_key = _rate_key(request.user.id)
        current_count = cache.get(rate_key, 0)
        if current_count >= OTP_RATE_LIMIT:
            return Response(
                {"error": "Too many OTP requests. Please wait 10 minutes before trying again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Generate and store OTP
        otp = _generate_otp()
        cache.set(_otp_key(purpose, request.user.id), otp, timeout=OTP_TTL)

        # Increment rate counter (set with TTL only on first increment)
        if current_count == 0:
            cache.set(rate_key, 1, timeout=OTP_RATE_TTL)
        else:
            cache.incr(rate_key)

        # Send SMS
        send_otp_sms(digits, otp)

        logger.info(f"OTP sent - User: {request.user.id}, Purpose: {purpose}, Phone: {digits[:6]}****")
        return Response({"message": "OTP sent successfully", "expires_in": OTP_TTL}, status=status.HTTP_200_OK)


class UpdatePhoneView(APIView):
    """
    PATCH /api/accounts/update-phone/
    Body: { "phone": "9876543210", "otp": "123456" }
    Verifies OTP from Redis then updates user's phone number.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        phone = request.data.get("phone", "").strip()
        otp_input = request.data.get("otp", "").strip()

        if not phone or not otp_input:
            return Response(
                {"error": "phone and otp are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalize phone
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) != 10:
            return Response(
                {"error": "Phone must be a valid 10-digit Indian mobile number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify OTP
        if not verify_otp("phone_change", request.user.id, otp_input):
            return Response(
                {"error": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check phone is not already used by another account
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(phone_number=digits, is_phone_verified=True).exclude(pk=request.user.pk).exists():
            return Response(
                {"error": "This phone number is already registered to another account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update phone and mark as verified
        request.user.phone_number = digits
        request.user.is_phone_verified = True
        request.user.save(update_fields=["phone_number", "is_phone_verified"])

        logger.info(f"Phone updated - User: {request.user.id}, New phone: {digits[:6]}****")
        return Response(
            {"message": "Phone number updated successfully", "phone_number": digits},
            status=status.HTTP_200_OK,
        )


# ── MSG91 Widget helpers ──────────────────────────────────────────────────

def verify_msg91_access_token(access_token):
    """
    Verify a MSG91 OTP widget access token server-side.
    Returns (True, phone_number) on success, (False, error_message) on failure.
    """
    import requests as req
    from django.conf import settings
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', '')
    if not auth_key:
        logger.error("MSG91_AUTH_KEY not configured")
        return False, "OTP service not configured"
    try:
        resp = req.post(
            'https://control.msg91.com/api/v5/widget/verifyAccessToken',
            json={'authkey': auth_key, 'access-token': access_token},
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
        data = resp.json()
        if data.get('type') == 'success':
            # Extract phone from message field — MSG91 returns "91XXXXXXXXXX"
            raw = data.get('message', '')
            phone = raw.lstrip('+').lstrip('91') if raw else ''
            if len(phone) == 10:
                return True, phone
            return True, raw
        logger.warning(f"MSG91 token verify failed: {data}")
        return False, data.get('message', 'OTP verification failed')
    except Exception as e:
        logger.error(f"MSG91 token verify error: {e}")
        return False, "OTP verification failed. Please try again."


class UpdatePhoneMsg91View(APIView):
    """
    PATCH /api/accounts/update-phone-msg91/
    Body: { "phone": "9876543210", "access_token": "<msg91_jwt>" }
    Verifies MSG91 widget access token then updates user's phone number.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        phone = request.data.get("phone", "").strip()
        access_token = request.data.get("access_token", "").strip()

        if not phone or not access_token:
            return Response(
                {"error": "phone and access_token are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if len(digits) != 10:
            return Response(
                {"error": "Phone must be a valid 10-digit Indian mobile number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok, result = verify_msg91_access_token(access_token)
        if not ok:
            return Response({"error": result}, status=status.HTTP_400_BAD_REQUEST)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(phone_number=digits, is_phone_verified=True).exclude(pk=request.user.pk).exists():
            return Response(
                {"error": "This phone number is already registered to another account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.phone_number = digits
        request.user.is_phone_verified = True
        request.user.save(update_fields=["phone_number", "is_phone_verified"])

        logger.info(f"Phone updated via MSG91 - User: {request.user.id}, Phone: {digits[:6]}****")
        return Response(
            {"message": "Phone number updated successfully", "phone_number": digits},
            status=status.HTTP_200_OK,
        )


# ── Registration OTP (pre-auth, AllowAny) ────────────────────────────────

def _reg_otp_key(phone):
    return f"otp:registration:{phone}"


def _reg_rate_key(phone):
    return f"otp_rate:reg:{phone}"


def _reg_verified_key(phone):
    return f"otp_verified:reg:{phone}"


class SendRegistrationOTPView(APIView):
    """
    POST /api/accounts/send-registration-otp/
    Body: { "phone": "9876543210" }
    Pre-auth endpoint — rate limited by phone number (not user ID).
    Generates OTP, stores in Redis, sends via SMS.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone", "").strip()

        if not phone:
            return Response({"error": "phone is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize phone
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) != 10:
            return Response(
                {"error": "Phone must be a valid 10-digit Indian mobile number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if phone is already verified on another account
        if User.objects.filter(phone_number=digits, is_phone_verified=True).exists():
            return Response(
                {"error": "This phone number is already registered with another account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rate limiting by phone number
        rate_key = _reg_rate_key(digits)
        current_count = cache.get(rate_key, 0)
        if current_count >= OTP_RATE_LIMIT:
            return Response(
                {"error": "Too many OTP requests. Please wait 10 minutes before trying again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Generate and store OTP
        otp = _generate_otp()
        cache.set(_reg_otp_key(digits), otp, timeout=OTP_TTL)

        # Increment rate counter
        if current_count == 0:
            cache.set(rate_key, 1, timeout=OTP_RATE_TTL)
        else:
            cache.incr(rate_key)

        # Send SMS
        send_otp_sms(digits, otp)

        logger.info(f"Registration OTP sent - Phone: {digits[:6]}****")
        return Response({"message": "OTP sent successfully", "expires_in": OTP_TTL}, status=status.HTTP_200_OK)


class VerifyRegistrationOTPView(APIView):
    """
    POST /api/accounts/verify-registration-otp/
    Body: { "phone": "9876543210", "otp": "123456" }
    Verifies registration OTP. On success, returns a one-time `otp_verified_token` (UUID)
    stored in Redis. The registration endpoint must include this token to prove phone ownership.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone", "").strip()
        otp_input = request.data.get("otp", "").strip()

        if not phone or not otp_input:
            return Response({"error": "phone and otp are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize phone
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) != 10:
            return Response(
                {"error": "Phone must be a valid 10-digit Indian mobile number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify OTP from Redis
        key = _reg_otp_key(digits)
        stored = cache.get(key)
        if not stored or stored != str(otp_input).strip():
            return Response(
                {"error": "Invalid or expired OTP. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete OTP (one-time use)
        cache.delete(key)

        # Generate a verification token and store in Redis
        verified_token = str(uuid.uuid4())
        cache.set(_reg_verified_key(digits), verified_token, timeout=REG_OTP_VERIFIED_TTL)

        logger.info(f"Registration OTP verified - Phone: {digits[:6]}****")
        return Response(
            {"message": "Phone verified successfully", "otp_verified_token": verified_token},
            status=status.HTTP_200_OK,
        )
