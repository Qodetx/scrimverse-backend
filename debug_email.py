import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.core.mail import send_mail  # noqa: E402

print("\n" + "=" * 70)
print("AWS SES Debug Test")
print("=" * 70)

print("\nRegion: AP-SOUTH-1 (Mumbai)")
print(f"SMTP Host: {settings.EMAIL_HOST}")
print(f"From: {settings.DEFAULT_FROM_EMAIL}")
print("To: vamshias59@gmail.com")

try:
    result = send_mail(
        subject="Test from Scrimverse",
        message="Test email",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=["vamshias59@gmail.com"],
        fail_silently=False,
    )
    print("\n[SUCCESS!] Email sent!")
    print(f"Result: {result}")

except Exception as e:
    print("\n[ERROR]")
    print(f"Error Type: {type(e).__name__}")
    print("\nFull Error Message:")
    print(str(e))
    print("\n" + "=" * 70)

    # Check if it mentions region
    error_msg = str(e)
    if "AP-SOUTH-1" in error_msg:
        print("\nThe error mentions AP-SOUTH-1 region.")
        print("Please verify emails in AP-SOUTH-1 (Mumbai), not AP-SOUTH-2!")
    elif "AP-SOUTH-2" in error_msg:
        print("\nThe error mentions AP-SOUTH-2 region.")
        print("But we're using AP-SOUTH-1. This is a configuration mismatch!")

    if "not verified" in error_msg.lower():
        print("\nEmails mentioned as not verified:")
        # Extract email addresses from error
        import re

        emails = re.findall(r"[\w\.-]+@[\w\.-]+", error_msg)
        for email in emails:
            print(f"  - {email}")

        print("\nIMPORTANT:")
        print("1. Go to AWS SES Console")
        print("2. Check region in top-right: Must be AP-SOUTH-1 (Mumbai)")
        print("3. Go to 'Verified identities'")
        print("4. Check if these emails show 'Verified' status")
        print("5. If not, verify them in AP-SOUTH-1 region")

    print("=" * 70)
