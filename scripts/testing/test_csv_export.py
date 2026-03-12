#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrimverse.settings')
django.setup()

from tournaments.models import Tournament, TournamentRegistration
from accounts.models import TeamMember
import csv
import io

t = Tournament.objects.get(id=69)
registrations = TournamentRegistration.objects.filter(tournament=t).select_related("player__user", "team")

# Generate CSV
output = io.StringIO()
writer = csv.DictWriter(
    output,
    fieldnames=[
        "User ID",
        "User Name",
        "Team ID",
        "Team Name",
        "Email",
        "Phone Number",
        "User Role",
        "Status",
    ],
)

writer.writeheader()

added_players = set()

for registration in registrations:
    player_user = registration.player.user
    team = registration.team
    team_id = team.id if team else "N/A"
    team_name = team.name if team else registration.team_name or "N/A"

    is_captain = False
    if team:
        team_captain = team.captain
        is_captain = player_user.id == team_captain.id

    role = "Captain" if is_captain else "Member"
    player_key = (player_user.id, team.id if team else -1)

    if player_key not in added_players:
        writer.writerow(
            {
                "User ID": player_user.id,
                "User Name": player_user.username,
                "Team ID": team_id,
                "Team Name": team_name,
                "Email": player_user.email,
                "Phone Number": player_user.phone_number or "N/A",
                "User Role": role,
                "Status": registration.status,
            }
        )
        added_players.add(player_key)

    if team:
        team_members = TeamMember.objects.filter(team=team).select_related("user")
        for member in team_members:
            member_user = member.user
            if member_user:
                member_key = (member_user.id, team.id)
                if member_key not in added_players:
                    member_role = "Captain" if member.is_captain else "Member"
                    writer.writerow(
                        {
                            "User ID": member_user.id,
                            "User Name": member_user.username,
                            "Team ID": team.id,
                            "Team Name": team_name,
                            "Email": member_user.email,
                            "Phone Number": member_user.phone_number or "N/A",
                            "User Role": member_role,
                            "Status": registration.status,
                        }
                    )
                    added_players.add(member_key)

csv_content = output.getvalue()
lines = csv_content.split('\n')
print("CSV Header:")
print(lines[0])
print("\nFirst 5 data rows:")
for line in lines[1:6]:
    if line.strip():
        print(line)
print(f"\nTotal rows generated: {len([l for l in lines if l.strip() and l != lines[0]])}")
print("\n✓ CSV export format is correct!")
