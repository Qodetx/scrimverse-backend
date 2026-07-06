"""
SMS utility for ScrimVerse.
Primary provider: MSG91 (reliable India delivery with DLT compliance).
Fallback: AWS SNS (used if MSG91 not configured or fails).
"""
import logging

import boto3
import requests as req
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


# ── MSG91 ──────────────────────────────────────────────────────────────────

def _send_via_msg91_otp(phone_number, otp_code):
    """
    Send OTP via MSG91.
    phone_number: 10-digit without country code.
    Returns True on success, False otherwise.
    """
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', '')
    template_id = getattr(settings, 'MSG91_TEMPLATE_ID', '')
    if not auth_key:
        return False
    try:
        response = req.post(
            'https://control.msg91.com/api/v5/otp',
            json={
                'template_id': template_id,
                'mobile': f'91{phone_number}',
                'authkey': auth_key,
                'otp': otp_code,
            },
            timeout=10,
        )
        data = response.json()
        if data.get('type') == 'success':
            logger.info(f"OTP SMS sent via MSG91 to +91{phone_number}, reqId: {data.get('request_id')}")
            return True
        logger.warning(f"MSG91 OTP failed for +91{phone_number}: {data}")
        return False
    except Exception as e:
        logger.error(f"MSG91 OTP error for +91{phone_number}: {e}")
        return False


def _send_via_msg91_sms(phone_number, message):
    """
    Send a plain SMS via MSG91 (used for team invites).
    phone_number: full number with country code e.g. +919876543210
    Returns True on success, False otherwise.
    """
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', '')
    if not auth_key:
        return False
    # Strip leading + for MSG91
    mobile = phone_number.lstrip('+')
    try:
        response = req.post(
            'https://control.msg91.com/api/v5/flow/',
            json={
                'authkey': auth_key,
                'sender': 'SCRMVS',
                'mobiles': mobile,
                'message': message,
            },
            timeout=10,
        )
        data = response.json()
        if data.get('type') == 'success':
            logger.info(f"SMS sent via MSG91 to {phone_number}, reqId: {data.get('request_id')}")
            return True
        logger.warning(f"MSG91 SMS failed for {phone_number}: {data}")
        return False
    except Exception as e:
        logger.error(f"MSG91 SMS error for {phone_number}: {e}")
        return False


# ── AWS SNS ────────────────────────────────────────────────────────────────

def get_sns_client():
    access_key = getattr(settings, 'AWS_SNS_ACCESS_KEY_ID', '')
    secret_key = getattr(settings, 'AWS_SNS_SECRET_ACCESS_KEY', '')
    region = getattr(settings, 'AWS_SNS_REGION', 'ap-south-2')
    if not access_key or not secret_key:
        logger.warning("AWS SNS credentials not configured.")
        return None
    return boto3.client(
        'sns',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def _send_via_sns(phone_number_e164, message):
    """
    Send SMS via AWS SNS.
    phone_number_e164: full number with country code e.g. +919876543210
    Returns True on success, False otherwise.
    """
    client = get_sns_client()
    if not client:
        return False
    try:
        response = client.publish(
            PhoneNumber=phone_number_e164,
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SenderID': {'DataType': 'String', 'StringValue': 'SCRMVS'},
                'AWS.SNS.SMS.SMSType': {'DataType': 'String', 'StringValue': 'Transactional'},
            }
        )
        logger.info(f"SMS sent via SNS to {phone_number_e164}, MessageId: {response.get('MessageId')}")
        return True
    except ClientError as e:
        logger.error(f"SNS SMS failed for {phone_number_e164}: {e}")
        return False


# ── Public API ─────────────────────────────────────────────────────────────

def send_otp_sms(phone_number, otp_code):
    """
    Send OTP SMS. MSG91 primary, SNS fallback.
    phone_number: 10-digit without country code.
    """
    logger.info(f"OTP for {phone_number}: {otp_code}")

    if _send_via_msg91_otp(phone_number, otp_code):
        return True

    logger.warning(f"MSG91 failed, falling back to SNS for +91{phone_number}")
    return _send_via_sns(f"+91{phone_number}",
                         f"Your ScrimVerse OTP is {otp_code}. Valid for 10 minutes. Do not share.")


def send_team_invite_sms(phone_number, captain_name, team_name, invite_token):
    """
    Send team invite SMS. MSG91 primary, SNS fallback.
    phone_number: full number with country code e.g. +919876543210
    """
    frontend_url = settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else "http://localhost:3000"
    accept_link = f"{frontend_url}/join-team/{invite_token}"
    message = (
        f"ScrimVerse: {captain_name} invited you to join team '{team_name}'! "
        f"Accept here: {accept_link}"
    )

    if _send_via_msg91_sms(phone_number, message):
        return True

    logger.warning(f"MSG91 failed, falling back to SNS for {phone_number}")
    return _send_via_sns(phone_number, message)


# ── MSG91 WhatsApp ─────────────────────────────────────────────────────────

def send_team_invite_whatsapp(phone_number, invite_token):
    """
    Send team invite via WhatsApp using approved Meta template.
    Template: "scrimverse_verification_alert"
    Body is static. "Join Team" CTA button URL = base_url + invite_token (dynamic suffix).
    phone_number: full number with country code e.g. +919876543210
    Returns True on success, False otherwise.

    BEFORE GOING LIVE: confirm with client:
      1. MSG91_WHATSAPP_FROM_NUMBER (WABA number in their MSG91 dashboard)
      2. MSG91_WHATSAPP_TEMPLATE_NAME (exact name as registered with Meta)
      3. Whether the CTA button URL suffix is the token only or the full URL
    """
    auth_key = getattr(settings, 'MSG91_AUTH_KEY', '')
    from_number = getattr(settings, 'MSG91_WHATSAPP_FROM_NUMBER', '')
    template_name = getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_NAME', 'scrimverse_verification_alert')

    if not auth_key or not from_number:
        logger.warning("MSG91 WhatsApp not configured (missing MSG91_WHATSAPP_FROM_NUMBER or MSG91_AUTH_KEY)")
        return False

    # Strip leading + for MSG91
    mobile = phone_number.lstrip('+')

    try:
        response = req.post(
            'https://api.msg91.com/api/v5.2/whatsapp/whatsapp-outbound-message/bulk/',
            headers={
                'Authkey': auth_key,
                'Content-Type': 'application/json',
            },
            json={
                "integrated_number": from_number,
                "content_type": "template",
                "payload": {
                    "messaging_product": "whatsapp",
                    "to": mobile,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": "en"},
                        "components": [
                            {
                                # CTA button: "Join Team" — URL suffix is the invite_token
                                # Template URL in Meta: https://scrimverse.com/join-team/{{1}}
                                "type": "button",
                                "sub_type": "url",
                                "index": 0,
                                "parameters": [
                                    {"type": "text", "text": invite_token}
                                ],
                            }
                        ],
                    },
                },
            },
            timeout=10,
        )
        data = response.json()
        if data.get('type') == 'success' or response.status_code == 200:
            logger.info(f"WhatsApp invite sent via MSG91 to {phone_number}")
            return True
        logger.warning(f"MSG91 WhatsApp failed for {phone_number}: {data}")
        return False
    except Exception as e:
        logger.error(f"MSG91 WhatsApp error for {phone_number}: {e}")
        return False
