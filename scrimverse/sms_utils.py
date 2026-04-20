"""
AWS SNS SMS utility for sending team invite SMS messages.
Requires AWS_SNS_ACCESS_KEY_ID, AWS_SNS_SECRET_ACCESS_KEY, AWS_SNS_REGION in settings.
"""
import logging

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


def get_sns_client():
    """Create and return an AWS SNS client."""
    access_key = getattr(settings, 'AWS_SNS_ACCESS_KEY_ID', '')
    secret_key = getattr(settings, 'AWS_SNS_SECRET_ACCESS_KEY', '')
    region = getattr(settings, 'AWS_SNS_REGION', 'ap-south-1')

    if not access_key or not secret_key:
        logger.warning("AWS SNS credentials not configured. SMS sending will be skipped.")
        return None

    return boto3.client(
        'sns',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def send_team_invite_sms(phone_number, captain_name, team_name, invite_token):
    """
    Send a team invite SMS via AWS SNS.

    Args:
        phone_number: Phone number with country code (e.g., +919876543210)
        captain_name: Username of the captain sending the invite
        team_name: Name of the team
        invite_token: Unique invite token for the accept link

    Returns:
        bool: True if SMS was sent successfully, False otherwise
    """
    frontend_url = settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else "http://localhost:3000"
    accept_link = f"{frontend_url}/join-team/{invite_token}"

    client = get_sns_client()
    if not client:
        logger.warning(f"SMS not sent to {phone_number} — AWS SNS not configured. Invite link: {accept_link}")
        return False

    message = (
        f"ScrimVerse: {captain_name} invited you to join team '{team_name}'! "
        f"Accept here: {accept_link}"
    )

    try:
        response = client.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SenderID': {
                    'DataType': 'String',
                    'StringValue': 'ScrimVerse'
                },
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional'
                }
            }
        )
        logger.info(f"SMS sent to {phone_number}, MessageId: {response.get('MessageId')}")
        return True
    except ClientError as e:
        logger.error(f"Failed to send SMS to {phone_number}: {e}")
        return False


def send_otp_sms(phone_number, otp_code):
    """
    Send an OTP SMS via AWS SNS.
    phone_number: 10-digit number without country code (e.g. '9876543210')
    otp_code: 6-digit string
    Returns True if sent, False otherwise.
    In dev (SNS not configured): logs OTP to console so developers can test.
    """
    # Always log OTP for dev visibility (masked in prod via log level)
    logger.info(f"OTP for {phone_number}: {otp_code}")

    client = get_sns_client()
    if not client:
        logger.warning(f"OTP SMS not sent to {phone_number} — AWS SNS not configured. OTP: {otp_code}")
        return False

    message = f"Your ScrimVerse OTP is {otp_code}. Valid for 10 minutes. Do not share this code."

    try:
        response = client.publish(
            PhoneNumber=f"+91{phone_number}",
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SenderID': {
                    'DataType': 'String',
                    'StringValue': 'ScrimVerse'
                },
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional'
                }
            }
        )
        logger.info(f"OTP SMS sent to +91{phone_number}, MessageId: {response.get('MessageId')}")
        return True
    except ClientError as e:
        logger.error(f"Failed to send OTP SMS to +91{phone_number}: {e}")
        return False
