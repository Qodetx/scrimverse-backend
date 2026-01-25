import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.core.mail import send_mail  # noqa: E402

print("\n" + "=" * 70)
print("AWS SES Email Test - Multiple Recipients")
print("=" * 70)

print("\nEmail Configuration:")
print(f"  EMAIL_HOST: {settings.EMAIL_HOST}")
print(f"  EMAIL_PORT: {settings.EMAIL_PORT}")
print(f"  EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
print(f"  EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
print(f"  DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

print("\n" + "=" * 70)
print("Sending Test Emails...")
print("=" * 70)

# Test emails
test_emails = ["vamshias59@gmail.com", "sukruthsateesh@gmail.com"]

print(f"\nRecipients: {', '.join(test_emails)}")
print(f"From: {settings.DEFAULT_FROM_EMAIL}")

print("\n[!] IMPORTANT: In sandbox mode, all emails must be verified!")
print("   Go to: https://console.aws.amazon.com/ses/")
print("   Region: AP-SOUTH-1 (Mumbai)")
print("   Verified identities -> Create identity -> Email address")
print("   Verify: vamshias59@gmail.com")
print("   Verify: sukruthsateesh@gmail.com")
print("   Click verification links in both inboxes\n")

success_count = 0
failed_emails = []

for email in test_emails:
    try:
        print(f"\nSending to {email}...", end=" ")
        result = send_mail(
            subject="Test Email from Scrimverse",
            message="This is a test email from Scrimverse. If you received this, AWS SES is working!",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        print("[SUCCESS]")
        success_count += 1

    except Exception as e:
        print("[FAILED]")
        failed_emails.append((email, str(e)))

print("\n" + "=" * 70)
if success_count == len(test_emails):
    print("[ALL EMAILS SENT SUCCESSFULLY!]")
    print("=" * 70)
    print(f"\n{success_count}/{len(test_emails)} emails sent successfully!")
    print("\nNext steps:")
    print("  1. Check both inboxes (might take 1-2 minutes)")
    print("  2. Check spam folders if not in inbox")
    print("  3. Run full test: python test_emails.py vamshias59@gmail.com")
    print("=" * 70 + "\n")

elif success_count > 0:
    print("[PARTIAL SUCCESS]")
    print("=" * 70)
    print(f"\n{success_count}/{len(test_emails)} emails sent successfully!")
    print("\nFailed emails:")
    for email, error in failed_emails:
        print(f"  - {email}")
        if "not verified" in error.lower():
            print("    Reason: Email not verified in AWS SES")
    print("=" * 70 + "\n")

else:
    print("[ALL EMAILS FAILED]")
    print("=" * 70)
    print("\nError details:")
    for email, error in failed_emails:
        print(f"\n  Email: {email}")
        print(f"  Error: {error[:100]}...")

    print("\n[Troubleshooting]")
    if any("not verified" in error.lower() for _, error in failed_emails):
        print("  - Emails not verified in AWS SES")
        print("  - Go to AWS SES Console (AP-SOUTH-1 region)")
        print("  - Verify both email addresses")
        print("  - Click verification links in inboxes")
    elif any("authentication" in error.lower() for _, error in failed_emails):
        print("  - SMTP authentication failed")
        print("  - Check IAM permissions")
    else:
        print("  - Check Django logs: logs/django.log")
        print("  - Verify .env configuration")

    print("=" * 70 + "\n")
    sys.exit(1)
