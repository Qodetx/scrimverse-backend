import json
from datetime import date, timedelta

from rest_framework.test import APIRequestFactory
from django.contrib.auth import get_user_model

from tournaments.views import BulkScheduleUpdateView
from tournaments.models import Tournament, Match

# Configure test
TID = 12
HOST_USER = None

print('Starting bulk-schedule test for tournament', TID)

try:
    t = Tournament.objects.get(id=TID)
except Exception as e:
    print('Tournament not found:', e)
    raise SystemExit(1)

host_profile = t.host
host_user = getattr(host_profile, 'user', None)
if not host_user:
    print('Host user not found on tournament.host')
    raise SystemExit(1)

# Collect up to 3 matches from tournament (any groups)
matches = list(Match.objects.filter(group__tournament=t).order_by('id')[:3])
if not matches:
    print('No matches found for tournament', TID)
    raise SystemExit(1)

print('Found matches:', [m.id for m in matches])

# Prepare payload: schedule them tomorrow with incremental times and distinct maps
base_date = (date.today() + timedelta(days=1)).isoformat()
base_hour = 18
maps = ['Breeze', 'Lotus', 'Breeze']

payload = []
for i, m in enumerate(matches):
    payload.append({
        'match_id': m.id,
        'scheduled_date': base_date,
        'scheduled_time': f"{base_hour + i:02d}:00:00",
        'map_name': maps[i % len(maps)],
    })

print('Payload:', json.dumps(payload, indent=2))

# Build DRF request and call view
factory = APIRequestFactory()
req = factory.put(f'/api/tournaments/{TID}/bulk-schedule/', data=json.dumps(payload), content_type='application/json')
# Attach host user for permission check
req.user = host_user

view = BulkScheduleUpdateView.as_view()
response = view(req, pk=TID)

print('Response status:', getattr(response, 'status_code', None))
print('Response data:', getattr(response, 'data', None))

# Print updated matches from DB
for m in matches:
    m.refresh_from_db()
    print('Match', m.id, 'scheduled_date', m.scheduled_date, 'scheduled_time', m.scheduled_time, 'map', m.map_name)

print('Bulk-schedule test complete')
