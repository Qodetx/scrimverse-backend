#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration

print("\n" + "="*80)
print("📊 UPDATING TOURNAMENT 84 PARTICIPANT COUNT")
print("="*80)

tournament = Tournament.objects.get(id=84)

# Count actual registrations
reg_count = TournamentRegistration.objects.filter(tournament=tournament).count()
print(f"\n✓ Current registrations in DB: {reg_count} players")

# Count unique teams
team_count = TournamentRegistration.objects.filter(tournament=tournament).values('team').distinct().count()
print(f"✓ Unique teams: {team_count}")

# Update the tournament's total_participants field
tournament.total_participants = reg_count
tournament.save()

print(f"\n✅ Updated tournament.total_participants to: {reg_count}")

# Check if there's a different field for teams count
print(f"\n📋 Tournament Fields:")
print(f"   max_participants: {tournament.max_participants}")
print(f"   total_participants: {tournament.total_participants}")

print("\n" + "="*80)
print("✅ DONE! Refresh your browser to see the updated count")
print("="*80)
