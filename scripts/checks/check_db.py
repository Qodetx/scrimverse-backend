#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, TeamMember, Team, TeamJoinRequest
from tournaments.models import Tournament, TournamentRegistration

# List all users
print("="*60)
print("USERS IN DATABASE:")
print("="*60)
users = User.objects.all()[:10]
for user in users:
    print(f"  {user.email} (ID: {user.id})")

print("\n" + "="*60)
print("TOURNAMENTS IN DATABASE:")
print("="*60)
tournaments = Tournament.objects.all()[:10]
for t in tournaments:
    print(f"  {t.title} (ID: {t.id}) - Fee: {t.entry_fee}")

print("\n" + "="*60)
print("TOURNAMENT REGISTRATIONS:")
print("="*60)
regs = TournamentRegistration.objects.all()[:10]
if regs.exists():
    for reg in regs:
        player_email = reg.player.user.email if reg.player and reg.player.user else "N/A"
        print(f"  ID: {reg.id}")
        print(f"    Player: {player_email}")
        print(f"    Tournament: {reg.tournament.title}")
        print(f"    Team ID: {reg.team_id}, Team: {reg.team.name if reg.team else 'NULL'}")
        print()
else:
    print("  No registrations found!")

print("\n" + "="*60)
print("TEAMS:")
print("="*60)
teams = Team.objects.all()[:10]
for team in teams:
    print(f"  Team: {team.name} (ID: {team.id})")
    members = TeamMember.objects.filter(team=team)
    for member in members:
        print(f"    - {member.user.email}")
    print()

print("\n" + "="*60)
print("TEAM JOIN REQUESTS (PENDING):")
print("="*60)
requests = TeamJoinRequest.objects.filter(status='pending')[:10]
if requests.exists():
    for req in requests:
        email_or_player = req.invited_email or (req.player.email if req.player else "Unknown")
        print(f"  {email_or_player} -> Team: {req.team.name} (ID: {req.team.id})")
else:
    print("  No pending join requests")
