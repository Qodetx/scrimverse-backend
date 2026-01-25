"""
Convert AWS IAM credentials to SES SMTP credentials
Run this script to convert your IAM Access Key to SMTP password

Usage:
    python convert_to_smtp_password.py <SECRET_ACCESS_KEY> <REGION>

Example:
    python convert_to_smtp_password.py wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY ap-south-2
"""

import base64
import hashlib
import hmac
import sys

# Values that are required to calculate the signature. These values should
# never change.
DATE = "11111111"
SERVICE = "ses"
MESSAGE = "SendRawEmail"
TERMINAL = "aws4_request"
VERSION = 0x04


def sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def calculate_key(secret_access_key, region):
    """Calculate the SMTP password from AWS Secret Access Key"""
    signature = sign(("AWS4" + secret_access_key).encode("utf-8"), DATE)
    signature = sign(signature, region)
    signature = sign(signature, SERVICE)
    signature = sign(signature, TERMINAL)
    signature = sign(signature, MESSAGE)
    signature_and_version = bytes([VERSION]) + signature
    smtp_password = base64.b64encode(signature_and_version)
    return smtp_password.decode("utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python convert_to_smtp_password.py <SECRET_ACCESS_KEY> <REGION>")
        print("\nExample:")
        print("  python convert_to_smtp_password.py wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY ap-south-2")
        print("\nYour region is: ap-south-2 (Asia Pacific - Hyderabad)")
        sys.exit(1)

    secret_access_key = sys.argv[1]
    region = sys.argv[2]

    smtp_password = calculate_key(secret_access_key, region)

    print("\n" + "=" * 70)
    print("AWS SES SMTP Credentials")
    print("=" * 70)
    print(f"\nSMTP Username: {sys.argv[1][:20]}... (use your ACCESS KEY ID)")
    print(f"SMTP Password: {smtp_password}")
    print(f"\nRegion: {region}")
    print(f"SMTP Host: email-smtp.{region}.amazonaws.com")
    print("SMTP Port: 587 (TLS)")
    print("\n" + "=" * 70)
    print("\nAdd these to your .env file:")
    print("=" * 70)
    print("EMAIL_HOST_USER=<YOUR_ACCESS_KEY_ID>")
    print(f"EMAIL_HOST_PASSWORD={smtp_password}")
    print(f"EMAIL_HOST=email-smtp.{region}.amazonaws.com")
    print("=" * 70 + "\n")
