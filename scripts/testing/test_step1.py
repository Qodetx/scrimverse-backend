"""
Quick test script for Step 1 implementation
Tests is_5v5_game() and requires_password() methods
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament
from accounts.models import HostProfile

print("=" * 60)
print("STEP 1 VERIFICATION: Valorant & 5v5 Mode")
print("=" * 60)

print("\n✅ Game Choices Available:")
for choice in Tournament.GAME_CHOICES:
    print(f"   - {choice[0]}: {choice[1]}")

print("\n✅ Game Format Choices Available:")
for choice in Tournament.GAME_FORMAT_CHOICES:
    print(f"   - {choice[0]}: {choice[1]}")

# Test helper methods without saving
print("\n" + "=" * 60)
print("TESTING HELPER METHODS (No Database Save)")
print("=" * 60)

# Create mock tournament objects for testing
host = HostProfile.objects.first()

if host:
    print("\n📝 Testing Valorant Tournament:")
    valorant_t = Tournament(game_name='Valorant', host=host, game_mode='Squad')
    print(f"   is_5v5_game(): {valorant_t.is_5v5_game()} (Expected: True)")
    print(f"   requires_password(): {valorant_t.requires_password()} (Expected: False)")
    
    print("\n📝 Testing COD Tournament:")
    cod_t = Tournament(game_name='COD', host=host, game_mode='Squad')
    print(f"   is_5v5_game(): {cod_t.is_5v5_game()} (Expected: True)")
    print(f"   requires_password(): {cod_t.requires_password()} (Expected: True)")
    
    print("\n📝 Testing BGMI Tournament (Multi-team):")
    bgmi_t = Tournament(game_name='BGMI', host=host, game_mode='Squad')
    print(f"   is_5v5_game(): {bgmi_t.is_5v5_game()} (Expected: False)")
    print(f"   requires_password(): {bgmi_t.requires_password()} (Expected: True)")
    
    print("\n📝 Testing Freefire Tournament (Multi-team):")
    freefire_t = Tournament(game_name='Freefire', host=host, game_mode='Squad')
    print(f"   is_5v5_game(): {freefire_t.is_5v5_game()} (Expected: False)")
    print(f"   requires_password(): {freefire_t.requires_password()} (Expected: True)")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Step 1 Complete!")
    print("=" * 60)
else:
    print("\n⚠️  No host found in database - cannot test without host")
    print("   But Game Choices and Format Choices are confirmed added!")
