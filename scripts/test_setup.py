#!/usr/bin/env python
"""
Simple test to verify Django setup
"""
import os
import sys

import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scrimverse.settings")
django.setup()

from accounts.models import Team  # noqa: E402

print("=" * 60)
print("Testing Django Setup")
print("=" * 60)
print(f"Total teams: {Team.objects.count()}")
print("Setup working!")
