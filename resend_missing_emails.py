import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from scrimverse.email_utils import (  # noqa: E402
    send_password_reset_email,
    send_premium_tournament_promo_email,
    send_tournament_registration_email,
    send_tournament_reminder_email,
)

print("\n" + "=" * 70)
print("Resending Missing Emails")
print("=" * 70)

test_email = "vamshias59@gmail.com"
results = []

# 1. Password Reset Email
print("\n1. Sending Password Reset Email...")
success = send_password_reset_email(
    user_email=test_email,
    user_name="Test User",
    reset_url="http://localhost:3000/reset-password/abc123",
)
results.append(("Password Reset Email", success))
print(f"   {'[SUCCESS]' if success else '[FAILED]'}")

# 2. Tournament Registration Email
print("\n2. Sending Tournament Registration Email...")
success = send_tournament_registration_email(
    user_email=test_email,
    user_name="Test Player",
    tournament_name="BGMI Championship 2026",
    game_name="BGMI",
    start_date="January 30, 2026 at 06:00 PM",
    registration_id="REG-12345",
    tournament_url="http://localhost:3000/tournaments/1",
    team_name="Team Alpha",
)
results.append(("Tournament Registration Email", success))
print(f"   {'[SUCCESS]' if success else '[FAILED]'}")

# 3. Premium Tournament Promo Email
print("\n3. Sending Premium Tournament Promo Email...")
success = send_premium_tournament_promo_email(
    user_email=test_email,
    user_name="Test Player",
    tournament_name="Premium BGMI Tournament",
    game_name="BGMI",
    prize_pool="Rs.50,000",
    registration_deadline="January 28, 2026",
    start_date="February 01, 2026 at 06:00 PM",
    tournament_url="http://localhost:3000/tournaments/2",
)
results.append(("Premium Tournament Promo Email", success))
print(f"   {'[SUCCESS]' if success else '[FAILED]'}")

# 4. Tournament Reminder Email
print("\n4. Sending Tournament Reminder Email...")
success = send_tournament_reminder_email(
    host_email=test_email,
    host_name="Gaming Org",
    tournament_name="BGMI Championship 2026",
    start_time="06:00 PM",
    total_registrations=75,
    tournament_manage_url="http://localhost:3000/host/tournaments/1",
)
results.append(("Tournament Reminder Email", success))
print(f"   {'[SUCCESS]' if success else '[FAILED]'}")

# Summary
print("\n" + "=" * 70)
print("Summary")
print("=" * 70)

success_count = sum(1 for _, success in results if success)
for name, success in results:
    status = "[SUCCESS]" if success else "[FAILED]"
    print(f"{status} - {name}")

print(f"\n{success_count}/4 emails sent successfully")
print(f"\nCheck your inbox: {test_email}")
print("Also check:")
print("  - Spam folder")
print("  - Promotions tab (Gmail)")
print("  - Updates tab (Gmail)")
print("\nEmails might take 1-2 minutes to arrive.")
print("=" * 70 + "\n")
