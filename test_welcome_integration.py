import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.conf import settings  # noqa: E402

from scrimverse.email_tasks import send_welcome_email_task  # noqa: E402

print("\n" + "=" * 70)
print("Testing Welcome Email Integration")
print("=" * 70)

# Test email
test_email = "vamshias59@gmail.com"

# Test 1: Player Welcome Email
print("\n1. Testing PLAYER Welcome Email...")
print(f"   Sending to: {test_email}")
print("   User type: PLAYER")

send_welcome_email_task.delay(
    user_email=test_email,
    user_name="Test Player",
    dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard",
    user_type="player",
)
print("   [QUEUED] Email task sent to Celery")

# Test 2: Host Welcome Email
print("\n2. Testing HOST Welcome Email...")
print(f"   Sending to: {test_email}")
print("   User type: HOST")

send_welcome_email_task.delay(
    user_email=test_email,
    user_name="Test Host",
    dashboard_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/host/dashboard",
    user_type="host",
)
print("   [QUEUED] Email task sent to Celery")

print("\n" + "=" * 70)
print("Test Complete!")
print("=" * 70)
print("\nWhat to check:")
print("  1. Check Celery worker terminal - should show task processing")
print("  2. Check your email inbox in 1-2 minutes")
print("  3. You should receive 2 emails:")
print("     - One for PLAYER registration")
print("     - One for HOST registration")
print("\nExpected differences:")
print("  - Player email: 'Player Account' + tournament features")
print("  - Host email: 'Host Account' + tournament management features")
print("=" * 70 + "\n")
