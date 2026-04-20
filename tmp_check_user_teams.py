import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()
from accounts.models import User, Team, TeamMember

user = User.objects.get(username='e2e_new_test')

print(f"--- Memberships for {user.username} (ID: {user.id}) ---")
memberships = TeamMember.objects.filter(user=user)
for m in memberships:
    print(f" Team: {m.team.name} | Game: {m.team.game} | Is Captain: {m.is_captain}")

print(f"\n--- Managed Teams (Captain) for {user.username} ---")
managed = Team.objects.filter(captain=user)
for t in managed:
    print(f" Team: {t.name} | Game: {t.game} | Created: {t.created_at}")
