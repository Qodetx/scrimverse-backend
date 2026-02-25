#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament

# Get both tournaments
bgmi_tournament = Tournament.objects.get(id=71)
valorant_tournament = Tournament.objects.get(id=72)

print("=" * 80)
print("💰 CONVERTING TOURNAMENTS TO FREE (0 ENTRY FEE)")
print("=" * 80)

# Update BGMI Tournament
print(f"\n📊 BGMI Tournament (ID: 71)")
print(f"  Before: Entry Fee = ₹{bgmi_tournament.entry_fee}")

bgmi_tournament.entry_fee = 0.00
bgmi_tournament.save()

print(f"  ✅ After: Entry Fee = ₹{bgmi_tournament.entry_fee}")

# Update Valorant Tournament
print(f"\n📊 Valorant Tournament (ID: 72)")
print(f"  Before: Entry Fee = ₹{valorant_tournament.entry_fee}")

valorant_tournament.entry_fee = 0.00
valorant_tournament.save()

print(f"  ✅ After: Entry Fee = ₹{valorant_tournament.entry_fee}")

print("\n" + "=" * 80)
print("✨ BOTH TOURNAMENTS ARE NOW FREE!")
print("=" * 80)
print(f"\n✅ Entry Fees removed - testing flow unblocked")
print(f"   • BGMI Squad 4v4 (ID: 71) → Entry Fee: ₹0.00")
print(f"   • Valorant 5v5 (ID: 72) → Entry Fee: ₹0.00")
print(f"\n📝 Prize pools remain unchanged:")
print(f"   • BGMI: ₹50,000")
print(f"   • Valorant: ₹100,000")
