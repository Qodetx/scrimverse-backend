#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration, Group, Match, MatchScore
from django.db.models import Sum

# Check tournament structure
t = Tournament.objects.get(id=64)
print("=" * 60)
print(f"TOURNAMENT: {t.title} (ID: {t.id})")
print(f"Status: {t.status}, Current Round: {t.current_round}")
print(f"Total Rounds: {len(t.rounds)}")
print(f"Round Structure: {t.rounds}")
print("=" * 60)

# Check Round 1 groups/lobbies
print("\n[ROUND 1 - LOBBIES]")
round1_groups = Group.objects.filter(tournament=t, round_number=1)
print(f"Total Groups: {round1_groups.count()}")
winners_list = []
for group in round1_groups:
    teams = group.teams.all()
    print(f"  - {group.group_name}: {group.teams.count()} teams")
    print(f"    Teams: {[team.team.name for team in teams]}")
    print(f"    Winner: {group.winner.team.name if group.winner else 'Not determined'}")
    if group.winner:
        winners_list.append(group.winner)

# Check TournamentRegistration for Round 2
print("\n[REGISTRATIONS FOR ROUND 2 - BEFORE CONFIG]")
round2_regs = TournamentRegistration.objects.filter(tournament=t, round_number=2)
print(f"Round 2 Registrations: {round2_regs.count()}")
for reg in round2_regs:
    print(f"  - {reg.team.name}: status={reg.status}")

print(f"\n[WINNERS FROM ROUND 1]")
print(f"Total winners: {len(winners_list)}")
for winner in winners_list:
    print(f"  - {winner.team.name}")

# Check Round 1 registrations to see bye team
print("\n[ROUND 1 - REGISTRATIONS (Full list)]")
round1_regs = TournamentRegistration.objects.filter(tournament=t, round_number=1)
print(f"Total Round 1 registrations: {round1_regs.count()}")
for reg in round1_regs:
    print(f"  - {reg.team.name}: status={reg.status}")

print("\n[ISSUE ANALYSIS]")
print(f"Winners found from lobbies: {len(winners_list)}")
print(f"Expected Round 2 teams: 4 (3 winners + 1 bye)")
print(f"Actual Round 2 registrations: {round2_regs.count()}")


