import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from django.utils import timezone  # noqa: E402

from scrimverse.email_utils import (  # noqa: E402
    send_host_approved_email,
    send_password_changed_email,
    send_password_reset_email,
    send_premium_tournament_promo_email,
    send_registration_limit_reached_email,
    send_tournament_completed_email,
    send_tournament_created_email,
    send_tournament_registration_email,
    send_tournament_reminder_email,
    send_tournament_results_email,
    send_welcome_email,
)


def test_all_emails(test_email):
    """Test all email templates"""

    print(f"\n{'='*60}")
    print("Testing AWS SES Email Integration")
    print(f"Test Email: {test_email}")
    print(f"{'='*60}\n")

    results = []

    # 1. Welcome Email
    print("1. Testing Welcome Email...")
    success = send_welcome_email(
        user_email=test_email, user_name="Test User", dashboard_url="http://localhost:3000/dashboard"
    )
    results.append(("Welcome Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 2. Password Reset Email
    print("2. Testing Password Reset Email...")
    success = send_password_reset_email(
        user_email=test_email, user_name="Test User", reset_url="http://localhost:3000/reset-password/abc123"
    )
    results.append(("Password Reset Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 3. Password Changed Email
    print("3. Testing Password Changed Email...")
    success = send_password_changed_email(
        user_email=test_email,
        user_name="Test User",
        changed_at=timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        ip_address="192.168.1.1",
        dashboard_url="http://localhost:3000/dashboard",
    )
    results.append(("Password Changed Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 4. Tournament Registration Email
    print("4. Testing Tournament Registration Email...")
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
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 5. Tournament Results Email
    print("5. Testing Tournament Results Email...")
    success = send_tournament_results_email(
        user_email=test_email,
        user_name="Test Player",
        tournament_name="BGMI Championship 2026",
        position=2,
        total_participants=50,
        results_url="http://localhost:3000/tournaments/1/results",
        team_name="Team Alpha",
    )
    results.append(("Tournament Results Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 6. Premium Tournament Promo Email
    print("6. Testing Premium Tournament Promo Email...")
    success = send_premium_tournament_promo_email(
        user_email=test_email,
        user_name="Test Player",
        tournament_name="Premium BGMI Tournament",
        game_name="BGMI",
        prize_pool="₹50,000",
        registration_deadline="January 28, 2026",
        start_date="February 01, 2026 at 06:00 PM",
        tournament_url="http://localhost:3000/tournaments/2",
    )
    results.append(("Premium Tournament Promo Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 7. Host Approved Email
    print("7. Testing Host Approved Email...")
    success = send_host_approved_email(
        user_email=test_email,
        user_name="Test Host",
        host_name="Gaming Org",
        approved_at=timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        host_dashboard_url="http://localhost:3000/host/dashboard",
    )
    results.append(("Host Approved Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 8. Tournament Created Email
    print("8. Testing Tournament Created Email...")
    success = send_tournament_created_email(
        host_email=test_email,
        host_name="Gaming Org",
        tournament_name="BGMI Championship 2026",
        game_name="BGMI",
        start_date="January 30, 2026 at 06:00 PM",
        max_participants=100,
        plan_type="PREMIUM",
        tournament_url="http://localhost:3000/tournaments/1",
        tournament_manage_url="http://localhost:3000/host/tournaments/1",
    )
    results.append(("Tournament Created Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 9. Tournament Reminder Email
    print("9. Testing Tournament Reminder Email...")
    success = send_tournament_reminder_email(
        host_email=test_email,
        host_name="Gaming Org",
        tournament_name="BGMI Championship 2026",
        start_time="06:00 PM",
        total_registrations=75,
        tournament_manage_url="http://localhost:3000/host/tournaments/1",
    )
    results.append(("Tournament Reminder Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 10. Registration Limit Reached Email
    print("10. Testing Registration Limit Reached Email...")
    success = send_registration_limit_reached_email(
        host_email=test_email,
        host_name="Gaming Org",
        tournament_name="BGMI Championship 2026",
        total_registrations=100,
        max_participants=100,
        start_date="January 30, 2026 at 06:00 PM",
        tournament_manage_url="http://localhost:3000/host/tournaments/1",
    )
    results.append(("Registration Limit Reached Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # 11. Tournament Completed Email
    print("11. Testing Tournament Completed Email...")
    success = send_tournament_completed_email(
        host_email=test_email,
        host_name="Gaming Org",
        tournament_name="BGMI Championship 2026",
        completed_at=timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_participants=95,
        total_matches=25,
        winner_name="Team Alpha",
        runner_up_name="Team Beta",
        total_registrations=100,
        results_published=True,
        tournament_manage_url="http://localhost:3000/host/tournaments/1",
    )
    results.append(("Tournament Completed Email", success))
    print(f"   {'✅ Success' if success else '❌ Failed'}\n")

    # Print Summary
    print(f"\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}\n")

    success_count = sum(1 for _, success in results if success)
    total_count = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\n{'='*60}")
    print(f"Results: {success_count}/{total_count} emails sent successfully")
    print(f"{'='*60}\n")

    if success_count == total_count:
        print("🎉 All tests passed! Check your email inbox.")
        print(f"📧 You should receive {total_count} emails at {test_email}")
    else:
        print("⚠️  Some tests failed. Check the logs for errors.")
        print("Common issues:")
        print("  - SMTP credentials not configured in .env")
        print("  - Email address not verified (sandbox mode)")
        print("  - AWS SES service issues")

    print("\n💡 Next Steps:")
    print("  1. Check your email inbox")
    print("  2. Check Django logs: logs/django.log")
    print("  3. Check AWS SES Console: Sending statistics")
    print("  4. If in sandbox mode, verify the recipient email")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_emails.py <your-verified-email@example.com>")
        print("\nExample:")
        print("  python test_emails.py test@example.com")
        sys.exit(1)

    test_email = sys.argv[1]

    # Validate email format
    if "@" not in test_email:
        print("❌ Invalid email address")
        sys.exit(1)

    # Run tests
    test_all_emails(test_email)
