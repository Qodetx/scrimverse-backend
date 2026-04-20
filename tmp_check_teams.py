import os
import django
import sys

# Set up Django environment
sys.path.append(r'c:\Users\Kishan B M\scrimverse-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from teams.models import Team, TeamMember
from users.models import User

def check_tester_teams():
    try:
        user = User.objects.get(email='tester@scrimverse.com')
        print(f"User: {user.email} (ID: {user.id})")
        
        teams = Team.objects.filter(members__user=user).distinct()
        print(f"Found {teams.count()} teams for this user:")
        
        for team in teams:
            member = TeamMember.objects.get(team=team, user=user)
            print(f"- Team: {team.name}")
            print(f"  ID: {team.id}")
            print(f"  Is Temporary: {team.is_temporary}")
            print(f"  Role: {member.role}")
            print(f"  Members: {[m.user.email if m.user else 'No User' for m in team.members.all()]}")
            print("-" * 20)
            
    except User.DoesNotExist:
        print("User tester@scrimverse.com not found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_tester_teams()
