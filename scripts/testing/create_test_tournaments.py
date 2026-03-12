"""
Script to create test tournaments and scrims for all scenarios.

This script creates:
- 3 plan types (basic, featured, premium) for each scenario
- 3 status types (upcoming, ongoing, completed)
- 3 registration states for upcoming (not started, open, ended)

Total: 27 tournaments + 27 scrims = 54 test events

Run with: python manage.py shell < scripts/create_test_tournaments.py
Or: python scripts/create_test_tournaments.py
"""

import os
import sys
from datetime import datetime, timedelta

import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from accounts.models import HostProfile, User  # noqa: E402
from tournaments.models import Tournament  # noqa: E402


def get_or_create_host():
    """Get or create a test host user."""
    try:
        host_user = User.objects.filter(user_type="host").first()
        if not host_user:
            host_user = User.objects.create_user(
                username="testhost", email="testhost@scrimverse.com", password="testpass123", user_type="host"
            )
            print(f"✓ Created test host user: {host_user.username}")

        host_profile = HostProfile.objects.filter(user=host_user).first()
        if not host_profile:
            host_profile = HostProfile.objects.create(
                user=host_user, organization_name="Test Gaming Org", verification_status="approved"
            )
            print(f"✓ Created host profile for: {host_user.username}")

        return host_profile
    except Exception as e:
        print(f"✗ Error creating host: {e}")
        return None


def create_tournament(host, event_mode, plan_type, status, reg_status=None):
    """Create a tournament with specific parameters."""
    now = datetime.now()

    # Set up times based on status and registration status
    if status == "upcoming":
        if reg_status == "not_started":
            # Registration starts in 2 days
            reg_start = now + timedelta(days=2)
            reg_end = now + timedelta(days=5)
            tournament_start = now + timedelta(days=7)
        elif reg_status == "open":
            # Registration is currently open
            reg_start = now - timedelta(days=1)
            reg_end = now + timedelta(days=3)
            tournament_start = now + timedelta(days=5)
        else:  # ended
            # Registration ended yesterday
            reg_start = now - timedelta(days=5)
            reg_end = now - timedelta(days=1)
            tournament_start = now + timedelta(days=2)
    elif status == "ongoing":
        # Tournament started yesterday
        reg_start = now - timedelta(days=10)
        reg_end = now - timedelta(days=5)
        tournament_start = now - timedelta(days=1)
    else:  # completed
        # Tournament ended 3 days ago
        reg_start = now - timedelta(days=15)
        reg_end = now - timedelta(days=10)
        tournament_start = now - timedelta(days=5)

    tournament_end = tournament_start + timedelta(hours=6)

    # Create title
    mode_name = "Scrim" if event_mode == "SCRIM" else "Tournament"
    status_name = reg_status.replace("_", " ").title() if reg_status else status.title()
    title = f"{plan_type.title()} {mode_name} - {status_name}"

    # Set max participants based on event mode
    max_participants = 25 if event_mode == "SCRIM" else 100

    # Create rounds structure as JSON
    if event_mode == "SCRIM":
        rounds_data = [{"round": 1, "max_teams": max_participants, "qualifying_teams": 0}]
    else:
        rounds_data = [
            {"round": 1, "max_teams": max_participants, "qualifying_teams": 50},
            {"round": 2, "max_teams": 50, "qualifying_teams": 20},
            {"round": 3, "max_teams": 20, "qualifying_teams": 1},
        ]

    try:
        tournament = Tournament.objects.create(
            host=host,
            title=title,
            game_name="BGMI",
            game_mode="Squad",
            prize_pool=10000 if plan_type == "basic" else (50000 if plan_type == "featured" else 100000),
            entry_fee=100 if plan_type == "basic" else (200 if plan_type == "featured" else 500),
            max_participants=max_participants,
            tournament_start=tournament_start,
            tournament_end=tournament_end,
            registration_start=reg_start,
            registration_end=reg_end,
            description=f"Test {plan_type} {mode_name.lower()} in {status} status",
            rules="Standard tournament rules apply.",
            status=status,
            event_mode=event_mode,
            plan_type=plan_type,
            is_featured=(plan_type in ["featured", "premium"]),
            current_round=1 if status == "ongoing" else 0,
            rounds=rounds_data,
        )

        return tournament
    except Exception as e:
        print(f"✗ Error creating {title}: {e}")
        return None


def main():
    """Main function to create all test data."""
    print("\n" + "=" * 60)
    print("Creating Test Tournaments and Scrims")
    print("=" * 60 + "\n")

    # Get or create host
    host = get_or_create_host()
    if not host:
        print("\n✗ Failed to create host. Exiting.")
        return

    print(f"\n✓ Using host: {host.user.username}\n")

    # Delete existing test tournaments
    print("Cleaning up old test data...")
    Tournament.objects.filter(host=host).delete()
    print("✓ Cleaned up old test data\n")

    plan_types = ["premium", "featured", "basic"]
    event_modes = [("TOURNAMENT", "Tournament"), ("SCRIM", "Scrim")]

    created_count = 0

    # Create tournaments for each scenario
    for event_mode, mode_name in event_modes:
        print(f"\n{'─'*60}")
        print(f"Creating {mode_name}s")
        print(f"{'─'*60}\n")

        for plan_type in plan_types:
            print(f"\n  {plan_type.upper()} Plan:")

            # UPCOMING - Registration Not Started
            tournament = create_tournament(host, event_mode, plan_type, "upcoming", "not_started")
            if tournament:
                print(f"    ✓ Created: {tournament.title}")
                created_count += 1

            # UPCOMING - Registration Open
            tournament = create_tournament(host, event_mode, plan_type, "upcoming", "open")
            if tournament:
                print(f"    ✓ Created: {tournament.title}")
                created_count += 1

            # UPCOMING - Registration Ended
            tournament = create_tournament(host, event_mode, plan_type, "upcoming", "ended")
            if tournament:
                print(f"    ✓ Created: {tournament.title}")
                created_count += 1

            # ONGOING
            tournament = create_tournament(host, event_mode, plan_type, "ongoing")
            if tournament:
                print(f"    ✓ Created: {tournament.title}")
                created_count += 1

            # COMPLETED
            tournament = create_tournament(host, event_mode, plan_type, "completed")
            if tournament:
                print(f"    ✓ Created: {tournament.title}")
                created_count += 1

    print("\n" + "=" * 60)
    print(f"Summary: Created {created_count} test events")
    print("=" * 60)

    # Print breakdown
    print("\nBreakdown:")
    print(f"  • Tournaments: {Tournament.objects.filter(host=host, event_mode='TOURNAMENT').count()}")
    print(f"  • Scrims: {Tournament.objects.filter(host=host, event_mode='SCRIM').count()}")
    print("\nBy Status:")
    print(f"  • Upcoming: {Tournament.objects.filter(host=host, status='upcoming').count()}")
    print(f"  • Ongoing: {Tournament.objects.filter(host=host, status='ongoing').count()}")
    print(f"  • Completed: {Tournament.objects.filter(host=host, status='completed').count()}")
    print("\nBy Plan Type:")
    print(f"  • Basic: {Tournament.objects.filter(host=host, plan_type='basic').count()}")
    print(f"  • Featured: {Tournament.objects.filter(host=host, plan_type='featured').count()}")
    print(f"  • Premium: {Tournament.objects.filter(host=host, plan_type='premium').count()}")

    print("\n✓ All test data created successfully!")
    print("\nYou can now test:")
    print("  • /tournaments page")
    print("  • /scrims page")
    print("  • All badge types (basic, featured, premium)")
    print("  • All status types (upcoming, active, past)")
    print("  • All registration states (not started, open, ended)")
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
