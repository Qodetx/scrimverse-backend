import os
import django
import sys

# Set up Django environment
sys.path.append(r'c:\Users\Kishan B M\scrimverse-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import Team, TeamJoinRequest
from tournaments.models import TournamentRegistration

def check_invites():
    print("--- Team Join Requests (Invites) ---")
    reqs = TeamJoinRequest.objects.all().order_by('-created_at')[:5]
    for r in reqs:
        print(f"ID: {r.id} | Team: {r.team.name} | Email: {r.invited_email} | Status: {r.status} | Token: {r.invite_token}")
    
    print("\n--- Tournament Registrations (Invites) ---")
    regs = TournamentRegistration.objects.all().order_by('-registered_at')[:5]
    for reg in regs:
        print(f"ID: {reg.id} | Tournament: {reg.tournament.title} | Team Name: {reg.team_name} | Temp Emails: {reg.temp_teammate_emails}")

if __name__ == "__main__":
    check_invites()
