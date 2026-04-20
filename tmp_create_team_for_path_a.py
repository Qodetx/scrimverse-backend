import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()
from accounts.models import User, Team, TeamMember, PlayerProfile

user = User.objects.get(username='e2e_new_test')
profile = user.player_profile

# Create a permanent BGMI team
team, created = Team.objects.get_or_create(
    name="E2E Legends",
    captain=user,
    defaults={
        'game': 'BGMI',
        'is_temporary': False,
        'description': 'Permanent team for E2E testing'
    }
)

if created:
    # Add captain as a member
    TeamMember.objects.create(team=team, user=user, username=user.username, is_captain=True)
    
    # Add some dummy members so we can "pick players" in the UI
    users = [
        ('kishannnn', 'kishanbm25000@gmail.com'),
        ('kishannn', 'kishanbm2500@gmail.com'),
        ('tester_player', 'tester@scrimverse.com')
    ]
    
    for username, email in users:
        try:
            u = User.objects.get(username=username)
            TeamMember.objects.create(team=team, user=u, username=username, is_captain=False)
        except:
            TeamMember.objects.create(team=team, username=username, is_captain=False)

    print(f"✅ Created permanent team 'E2E Legends' for {user.username}")
else:
    print(f"ℹ️ Team 'E2E Legends' already exists.")
