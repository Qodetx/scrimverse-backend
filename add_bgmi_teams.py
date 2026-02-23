#!/usr/bin/env python
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User, PlayerProfile, Team
from tournaments.models import Tournament, TournamentRegistration

t = Tournament.objects.get(id=68)

team_names = [
    "Soul Snippers", "GodL Esports", "Blind Esports", "OR Esports",
    "Team XO", "Team Insane", "Marcos Gaming", "Team Mayhem",
    "Gladiators Esports", "Team IND", "Stalwart Esports", "Velocity Gaming",
]

for i, team_name in enumerate(team_names):
    username = f"bgmi_p{i+1}"
    user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@test.com", "user_type": "player"})
    player, _ = PlayerProfile.objects.get_or_create(user=user)
    team, _ = Team.objects.get_or_create(name=team_name, defaults={"captain": user})
    reg, created = TournamentRegistration.objects.get_or_create(
        tournament=t, team=team,
        defaults={"player": player, "status": "confirmed", "team_name": team_name}
    )
    if not created:
        reg.status = "confirmed"
        reg.save()
    print(f"  [{i+1:2d}] {team_name} (reg ID: {reg.id})")

count = TournamentRegistration.objects.filter(tournament=t, status="confirmed").count()
t.current_participants = count
t.save(update_fields=["current_participants"])
print(f"\nDone! Confirmed teams: {count}/12")
print(f"Manage URL: http://localhost:3000/tournaments/{t.id}/manage")
