#!/usr/bin/env python
"""
Fix: Add bye team to selected_teams["1"] and update current_round to 2
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration, Group

t = Tournament.objects.get(id=64)

print("=" * 60)
print(f"TOURNAMENT: {t.title} (ID: {t.id})")
print(f"current_round: {t.current_round}")
print(f"selected_teams: {t.selected_teams}")
print(f"round_status: {t.round_status}")
print("=" * 60)

# Find all Round 1 team registration IDs
all_reg_ids = set(
    TournamentRegistration.objects.filter(tournament=t).values_list('id', flat=True)
)

# Find teams in lobbies for Round 1
lobby_team_ids = set()
for group in Group.objects.filter(tournament=t, round_number=1):
    for team in group.teams.all():
        lobby_team_ids.add(team.id)

print(f"\nAll registration IDs: {all_reg_ids}")
print(f"Teams in lobbies: {lobby_team_ids}")

# Bye team = registered but not in any lobby
bye_team_ids = all_reg_ids - lobby_team_ids
print(f"Bye team IDs: {bye_team_ids}")

for bye_id in bye_team_ids:
    reg = TournamentRegistration.objects.get(id=bye_id)
    print(f"  Bye team: {reg.team.name} (reg ID={reg.id})")

# Current selected_teams for round 1
current_selected = t.selected_teams.get('1', [])
print(f"\nCurrent selected_teams['1']: {current_selected}")

# Add bye team to selected_teams
all_round2_teams = current_selected + list(bye_team_ids)
print(f"After adding bye team: {all_round2_teams}")

# Apply fix
confirm = input("\nApply fix? (yes/no): ").strip().lower()
if confirm == 'yes':
    t.selected_teams['1'] = all_round2_teams
    t.current_round = 2
    t.save(update_fields=['selected_teams', 'current_round'])
    t.refresh_from_db()
    print("\n[FIXED]")
    print(f"  selected_teams: {t.selected_teams}")
    print(f"  current_round: {t.current_round}")
else:
    print("No changes made.")
