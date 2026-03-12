#!/usr/bin/env python
"""
Set registration_start to past and registration_end to future for specified tournament IDs.
Usage: python open_registrations_now.py 32 33 34 35
"""
import sys
import os
from datetime import timedelta

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
import django
django.setup()

from django.utils import timezone
from tournaments.models import Tournament

ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
if not ids:
    print("Provide tournament IDs to open registrations for.")
    sys.exit(1)

now = timezone.now()
updated = []
for tid in ids:
    try:
        t = Tournament.objects.get(id=tid)
        t.registration_start = now - timedelta(hours=1)
        t.registration_end = now + timedelta(days=7)
        # Also set tournament start a bit later to keep status sensible
        t.tournament_start = now + timedelta(days=3)
        t.tournament_end = now + timedelta(days=3, hours=4)
        t.save()
        updated.append(t.id)
        print(f"Updated tournament {t.id}: registration_start={t.registration_start}, registration_end={t.registration_end}")
    except Tournament.DoesNotExist:
        print(f"Tournament {tid} not found")

print(f"Done. Updated {len(updated)} tournaments: {updated}")
