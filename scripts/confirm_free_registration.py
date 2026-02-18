#!/usr/bin/env python
"""
Confirm a pending free registration and queue emails.
Usage: python confirm_free_registration.py <registration_id>
"""
import sys
import os

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
import django
django.setup()

from tournaments.models import TournamentRegistration
from tournaments.tasks import send_tournament_registration_email_task, update_host_dashboard_stats
from accounts.models import User
from django.conf import settings


def confirm_registration(reg_id):
    reg = TournamentRegistration.objects.get(id=reg_id)
    if reg.status == 'confirmed' and reg.payment_status:
        print(f"Registration {reg_id} already confirmed")
        return

    reg.payment_status = True
    reg.status = 'confirmed'

    # Populate team_members from temp_teammate_emails if empty
    if (not reg.team_members) and reg.temp_teammate_emails:
        team_members = []
        for email in reg.temp_teammate_emails:
            try:
                u = User.objects.get(email__iexact=email, user_type='player')
                team_members.append({
                    'email': email,
                    'username': u.username,
                    'player_id': getattr(u.player_profile, 'id', None),
                    'is_registered': True,
                })
            except Exception:
                team_members.append({
                    'email': email,
                    'username': None,
                    'player_id': None,
                    'is_registered': False,
                })
        reg.team_members = team_members

    reg.save()

    # Increment tournament participant count
    t = reg.tournament
    t.current_participants = (t.current_participants or 0) + 1
    t.save()

    # Trigger host dashboard update and send emails
    update_host_dashboard_stats.delay(t.host.id)

    send_tournament_registration_email_task.delay(
        user_email=reg.player.user.email,
        user_name=reg.player.user.username,
        tournament_name=t.title,
        game_name=t.game_name,
        start_date=t.tournament_start.strftime('%B %d, %Y at %I:%M %p'),
        registration_id=str(reg.id),
        tournament_url=f"{settings.FRONTEND_URL}/tournaments/{t.id}",
        team_name=reg.team_name,
    )

    # Send to registered teammates
    if reg.team_members:
        captain_name = reg.player.user.username
        for member in reg.team_members:
            if member.get('is_registered') and member.get('username') and member.get('username') != captain_name:
                try:
                    mu = User.objects.get(username=member.get('username'), user_type='player')
                    send_tournament_registration_email_task.delay(
                        user_email=mu.email,
                        user_name=mu.username,
                        tournament_name=t.title,
                        game_name=t.game_name,
                        start_date=t.tournament_start.strftime('%B %d, %Y at %I:%M %p'),
                        registration_id=str(reg.id),
                        tournament_url=f"{settings.FRONTEND_URL}/tournaments/{t.id}",
                        team_name=reg.team_name,
                    )
                except Exception:
                    continue

    print(f"Confirmed registration {reg.id} and queued emails")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python confirm_free_registration.py <registration_id>")
        sys.exit(1)
    rid = int(sys.argv[1])
    confirm_registration(rid)
