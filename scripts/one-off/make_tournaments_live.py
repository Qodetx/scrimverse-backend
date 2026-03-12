#!/usr/bin/env python
import os
import django
from django.utils import timezone
from datetime import timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament

# Get both tournaments
bgmi_tournament = Tournament.objects.get(id=71)
valorant_tournament = Tournament.objects.get(id=72)

now = timezone.now()
three_hours_later = now + timedelta(hours=3)

print("=" * 80)
print("🔄 UPDATING TOURNAMENTS TO LIVE MODE")
print("=" * 80)

# Update BGMI Tournament
print(f"\n📊 BGMI Tournament (ID: 71)")
print(f"  Current status: {bgmi_tournament.status}")

bgmi_tournament.status = 'ongoing'
bgmi_tournament.registration_start = now
bgmi_tournament.registration_end = three_hours_later
bgmi_tournament.tournament_start = now
bgmi_tournament.tournament_end = three_hours_later
bgmi_tournament.tournament_date = now.date()
bgmi_tournament.tournament_time = now.time()
bgmi_tournament.save()

print(f"  ✅ Updated status → ongoing")
print(f"  ✅ Registration: {bgmi_tournament.registration_start.strftime('%Y-%m-%d %H:%M:%S')} to {bgmi_tournament.registration_end.strftime('%H:%M:%S')}")
print(f"  ✅ Tournament: {bgmi_tournament.tournament_start.strftime('%Y-%m-%d %H:%M:%S')} to {bgmi_tournament.tournament_end.strftime('%H:%M:%S')}")

# Update Valorant Tournament
print(f"\n📊 Valorant Tournament (ID: 72)")
print(f"  Current status: {valorant_tournament.status}")

valorant_tournament.status = 'ongoing'
valorant_tournament.registration_start = now
valorant_tournament.registration_end = three_hours_later
valorant_tournament.tournament_start = now
valorant_tournament.tournament_end = three_hours_later
valorant_tournament.tournament_date = now.date()
valorant_tournament.tournament_time = now.time()
valorant_tournament.save()

print(f"  ✅ Updated status → ongoing")
print(f"  ✅ Registration: {valorant_tournament.registration_start.strftime('%Y-%m-%d %H:%M:%S')} to {valorant_tournament.registration_end.strftime('%H:%M:%S')}")
print(f"  ✅ Tournament: {valorant_tournament.tournament_start.strftime('%Y-%m-%d %H:%M:%S')} to {valorant_tournament.tournament_end.strftime('%H:%M:%S')}")

print("\n" + "=" * 80)
print("✨ BOTH TOURNAMENTS ARE NOW LIVE!")
print("=" * 80)
print(f"\n⏰ Time window: Now to {three_hours_later.strftime('%Y-%m-%d %H:%M:%S')} (3 hours)")
print(f"📍 You can test slowly within this window")
print(f"\nTournament IDs for testing:")
print(f"  • BGMI Squad 4v4 → ID: 71")
print(f"  • Valorant 5v5 → ID: 72")
