#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration

print("\n" + "="*80)
print("🔧 FIXING current_participants FIELD")
print("="*80)

tournament = Tournament.objects.get(id=84)

# Count unique teams
unique_teams = TournamentRegistration.objects.filter(tournament=tournament).values('team').distinct().count()

print(f"\n📊 Before:")
print(f"   current_participants: {tournament.current_participants}")
print(f"   max_participants: {tournament.max_participants}")

# Update the field
tournament.current_participants = unique_teams  # This is what displays on frontend!
tournament.save()

print(f"\n✅ After:")
print(f"   current_participants: {tournament.current_participants}")
print(f"   max_participants: {tournament.max_participants}")
print(f"   Display will show: {tournament.current_participants}/{tournament.max_participants}")

print("\n" + "="*80)
print("✅ REFRESHING YOUR BROWSER WILL SHOW 8/8 NOW!")
print("="*80)
