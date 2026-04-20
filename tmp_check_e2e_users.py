import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()
from accounts.models import User, Team
from tournaments.models import Tournament, TournamentRegistration

print("--- Test Player Users (recent 10) ---")
for u in User.objects.filter(user_type='player', is_active=True).order_by('-date_joined')[:10]:
    ev = getattr(u, 'is_email_verified', 'N/A')
    print(f"  {u.username} | {u.email} | ev={ev}")

print()
print("--- Recent Teams ---")
for t in Team.objects.all().order_by('-created_at')[:10]:
    try:
        cap = t.captain.user.username if t.captain else 'N/A'
    except Exception:
        cap = str(t.captain)
    print(f"  {t.name} | game={t.game} | temp={t.is_temporary} | captain={cap}")

print()
print("--- All Tournaments (recent 15) ---")
for t in Tournament.objects.all().order_by('-created_at')[:15]:
    print(f"  [{t.id}] {t.title[:60]} | mode={t.event_mode} | status={t.status} | fee={t.entry_fee}")
