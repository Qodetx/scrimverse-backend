import os
import sys

import django

from accounts.models import User
from tournaments.models import Scrim, ScrimRegistration, Tournament, TournamentRegistration

# Add the backend root (where manage.py lives) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()


def cleanup_test_accounts():
    """
    Deletes all test host and player accounts and related data
    (accounts created by automation with emails containing '@test.com').
    """
    test_users = User.objects.filter(email__icontains="@test.com")
    total = test_users.count()

    if total == 0:
        print("✅ No test accounts found.")
        return

    print(f"🧹 Found {total} test accounts to delete...\n")

    for user in test_users:
        user_type = user.user_type
        email = user.email

        if user_type == "host":
            if hasattr(user, "host_profile"):
                host_profile = user.host_profile
                # Delete tournaments hosted by this host
                tournaments = Tournament.objects.filter(host=host_profile)
                for t in tournaments:
                    # Delete related tournament registrations
                    TournamentRegistration.objects.filter(tournament=t).delete()
                    print(f"   🗑️ Deleted registrations for Tournament: {t.title}")
                    t.delete()
                    print(f"   🏁 Deleted Tournament: {t.title}")

                # Delete scrims hosted by this host
                scrims = Scrim.objects.filter(host=host_profile)
                for s in scrims:
                    ScrimRegistration.objects.filter(scrim=s).delete()
                    print(f"   🗑️ Deleted registrations for Scrim: {s.title}")
                    s.delete()
                    print(f"   🏁 Deleted Scrim: {s.title}")

                host_profile.delete()
                print(f"✅ Deleted host profile: {email}")

        elif user_type == "player":
            if hasattr(user, "player_profile"):
                player_profile = user.player_profile
                # Delete all tournament registrations by player
                TournamentRegistration.objects.filter(player=player_profile).delete()
                # Delete all scrim registrations by player
                ScrimRegistration.objects.filter(player=player_profile).delete()
                player_profile.delete()
                print(f"✅ Deleted player profile and registrations: {email}")

        # Finally delete the user
        user.delete()
        print(f"🧨 Deleted {user_type} account: {email}\n")

    print("\n✨ Cleanup complete! All test accounts and their related data removed successfully.")


if __name__ == "__main__":
    cleanup_test_accounts()
