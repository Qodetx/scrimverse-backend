#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament

try:
    t71 = Tournament.objects.get(id=71)
    t72 = Tournament.objects.get(id=72)
    print(f"Tournament 71: {t71.title}, Game: {t71.game_name}, Mode: {t71.game_mode}, is_5v5: {t71.is_5v5_game()}")
    print(f"Tournament 72: {t72.title}, Game: {t72.game_name}, Mode: {t72.game_mode}, is_5v5: {t72.is_5v5_game()}")
except Tournament.DoesNotExist as e:
    print(f"Error: {e}")
