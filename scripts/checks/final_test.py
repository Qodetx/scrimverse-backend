#!/usr/bin/env python
import os
import django
import requests
import base64

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from accounts.models import User

# Get user
u = User.objects.get(email='kishanbm2300@gmail.com')

# Get auth token if exists, or create a test request
print(f"Testing API for user: {u.email}")
print("=" * 60)

# Since we're testing locally, we can just import and call the view directly
from tournaments.views import PlayerTournamentRegistrationsView
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser

# Create a fake request
factory = RequestFactory()
request = factory.get('/api/tournaments/my-registrations/')
request.user = u

# Call the view
view = PlayerTournamentRegistrationsView.as_view()
response = view(request)

print(f"\nAPI Response Status: {response.status_code}")
print(f"API Response Data:\n{response.data}")

if response.status_code == 200:
    if isinstance(response.data, dict) and 'results' in response.data:
        registrations = response.data['results']
        print(f"\n✅ API returned {len(registrations)} registration(s)")
        for reg in registrations:
            print(f"   - {reg.get('tournament_title', 'Unknown')}")
    
    print("\n📝 NEXT STEPS:")
    print("1. Open your browser and go to http://localhost:3000")
    print(f"2. Login with: {u.email}")
    print("3. Go to Player Dashboard")
    print("4. Check 'Registered Matches' section")
    print("5. You should see 'Among Us Social Free' tournament listed!")
else:
    print(f"❌ API Error: {response.data}")
