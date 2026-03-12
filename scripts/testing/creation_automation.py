import json
import random
import string
import uuid
from datetime import datetime, timedelta

import requests

BASE_URL = "http://127.0.0.1:8000/api"
BANNER_IMAGE_PATH = "/Users/Sukruth30/Downloads/download.jpeg"


def random_email(prefix):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase, k=5))}@test.com"


def register_host():
    url = f"{BASE_URL}/accounts/host/register/"
    random_suffix = "".join(random.choices(string.ascii_lowercase, k=5))
    data = {
        "email": random_email("host"),
        "username": f"TestHost_{random_suffix}",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "phone_number": "9999999999",
    }
    res = requests.post(url, json=data)
    res = res.json()
    print("Host Registered:", res["user"]["email"])
    return res["tokens"]["access"], res["user"]


def create_tournament(token, game_mode, max_teams, title_suffix="", plan_type="basic"):
    url = f"{BASE_URL}/tournaments/create/"
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now()

    # Prepare form data
    # Note: max_participants field actually stores max_teams count
    data = {
        "title": f"Test Tournament - {game_mode}{title_suffix}",
        "description": f"Automated test tournament for {game_mode} mode.",
        "rules": "1. Play fair\n2. No hacks\n3. Respect opponents.",
        "game_name": "BGMI",
        "game_mode": game_mode,
        "max_participants": max_teams,  # This field stores max teams, not players
        "prize_pool": 10000,
        "entry_fee": 0,
        "registration_start": now.isoformat(),
        "registration_end": (now + timedelta(hours=6)).isoformat(),
        "tournament_start": (now + timedelta(days=1)).isoformat(),
        "tournament_end": (now + timedelta(days=2)).isoformat(),
        "plan_type": plan_type,  # basic, featured, or premium
        "rounds": [
            {"round": 1, "max_teams": 10, "qualifying_teams": 5},
            {"round": 2, "max_teams": 5, "qualifying_teams": 2},
            {"round": 3, "max_teams": 2, "qualifying_teams": 0},
        ],
    }

    # Prepare multipart form data with banner image
    files = {}
    try:
        with open(BANNER_IMAGE_PATH, "rb") as img:
            files = {"banner_image": ("download.jpeg", img, "image/jpeg")}
            # Convert rounds to JSON string for multipart form
            form_data = data.copy()
            form_data["rounds"] = json.dumps(data["rounds"])

            res = requests.post(url, data=form_data, files=files, headers=headers)
    except FileNotFoundError:
        print(f"Warning: Banner image not found at {BANNER_IMAGE_PATH}, creating without banner")
        res = requests.post(url, json=data, headers=headers)

    res = res.json()
    print(f"Tournament Created: {res['title']} | ID: {res['id']} | Mode: {game_mode}")
    return res["id"]


def create_player():
    """Create a single player and return their credentials"""
    player_email = random_email("player")
    url = f"{BASE_URL}/accounts/player/register/"
    unique_id = str(uuid.uuid4())[:8]

    data = {
        "email": player_email,
        "username": f"Player_{unique_id}",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "phone_number": "8888888888",
    }
    res = requests.post(url, json=data)

    if res.status_code != 201:
        print(f"ERROR: Failed to register player. Response: {res.text}")
        return None

    res_data = res.json()
    return {
        "email": player_email,
        "username": res_data["user"]["username"],
        "token": res_data["tokens"]["access"],
        "id": res_data["user"]["id"],
        "unique_id": unique_id,
    }


def create_team(captain_player, team_name, member_usernames):
    """Create a team with the captain and members"""
    url = f"{BASE_URL}/accounts/teams/"
    headers = {"Authorization": f"Bearer {captain_player['token']}"}

    data = {
        "name": team_name,
        "player_usernames": member_usernames,  # Includes captain and other members
    }

    res = requests.post(url, json=data, headers=headers)

    if res.status_code == 201:
        team_data = res.json()
        print(f"  ✅ Team created: {team_name} (ID: {team_data['id']})")
        return team_data["id"]
    else:
        print(f"  ❌ Failed to create team {team_name}: {res.text}")
        return None


def register_team_to_tournament(tournament_id, captain_player, team_id, save_as_team=True):
    """Register an existing team to a tournament"""
    register_url = f"{BASE_URL}/tournaments/{tournament_id}/register/"
    headers = {"Authorization": f"Bearer {captain_player['token']}"}

    reg_data = {
        "team_id": team_id,
        "save_as_team": save_as_team,  # Whether to save as permanent team
    }

    reg_response = requests.post(register_url, json=reg_data, headers=headers)
    if reg_response.status_code == 201:
        return True
    else:
        print(f"  ❌ Failed to register team: {reg_response.text}")
        return False


if __name__ == "__main__":
    print("=== Automating Tournament Setup ===\n")

    # Register host
    host_token, host_user = register_host()
    print()

    # Create tournaments
    print("\n--- Creating Tournaments ---")
    # Basic plan tournaments (2)
    squad_id = create_tournament(host_token, "Squad", 10, plan_type="basic")  # 10 teams - Basic
    duo_id = create_tournament(host_token, "Duo", 10, plan_type="basic")  # 10 teams - Basic

    # Featured plan tournaments (2)
    solo_id = create_tournament(host_token, "Solo", 10, plan_type="featured")  # 10 teams - Featured
    empty_duo_id = create_tournament(host_token, "Duo", 10, " (Empty)", plan_type="featured")  # 10 teams - Featured

    # Create 60 players upfront
    print("\n--- Creating 60 Players ---")
    all_players = []
    for i in range(60):
        player = create_player()
        if player:
            all_players.append(player)
            print(f"  Created player {i+1}/60: {player['email']}")

    print(f"\n✅ Created {len(all_players)} players successfully!")

    # Create teams first, then register them
    print("\n--- Creating Teams and Registering to Squad Tournament ---")
    squad_teams = []
    squad_players = []
    # Use first 40 players for Squad (10 teams of 4)
    for team_num in range(10):
        team_players = all_players[team_num * 4 : (team_num + 1) * 4]
        captain = team_players[0]
        team_name = f"Squad_Team_{team_num + 1}"

        # Get all usernames including captain
        member_usernames = [p["username"] for p in team_players]

        # Create team (first 7 teams saved, last 3 temporary)
        team_id = create_team(captain, team_name, member_usernames)

        if team_id:
            # Register to tournament (first 7 with save_as_team=True, last 3 with False)
            save_team = team_num < 7
            if register_team_to_tournament(squad_id, captain, team_id, save_as_team=save_team):
                print(
                    f"  ✅ Team {team_num + 1}/10 registered to Squad Tournament {'(Saved)' if save_team else '(Temporary)'}"  # noqa: E501
                )
                squad_teams.append({"name": team_name, "id": team_id, "saved": save_team})
                squad_players.extend([p["email"] for p in team_players])
            else:
                print(f"  ❌ Failed to register Team {team_num + 1}")

    # Use players 40-60 for Duo and Solo (20 players available)
    available_players = all_players[40:]  # Last 20 players who are not in any teams

    # Create and register teams for Duo tournament
    print("\n--- Creating Teams and Registering to Duo Tournament ---")
    duo_teams = []
    duo_players = []
    # Use first 10 available players for Duo (5 teams of 2)
    for team_num in range(5):
        if team_num * 2 + 1 >= len(available_players):
            break
        team_players = available_players[team_num * 2 : (team_num + 1) * 2]
        captain = team_players[0]
        team_name = f"Duo_Team_{team_num + 1}"

        member_usernames = [p["username"] for p in team_players]

        # Create team (first 3 teams saved, last 2 temporary)
        team_id = create_team(captain, team_name, member_usernames)

        if team_id:
            # Register to tournament
            save_team = team_num < 3
            if register_team_to_tournament(duo_id, captain, team_id, save_as_team=save_team):
                print(
                    f"  ✅ Team {team_num + 1}/5 registered to Duo Tournament {'(Saved)' if save_team else '(Temporary)'}"  # noqa: E501
                )
                duo_teams.append({"name": team_name, "id": team_id, "saved": save_team})
                duo_players.extend([p["email"] for p in team_players])
            else:
                print(f"  ❌ Failed to register Team {team_num + 1}")

    # For Solo, use the last 10 available players (players 50-60)
    print("\n--- Creating Teams and Registering to Solo Tournament ---")
    solo_teams = []
    solo_players = []
    # Use last 10 available players for Solo
    solo_players_pool = available_players[10:20] if len(available_players) >= 20 else available_players[10:]
    for i, player in enumerate(solo_players_pool):
        team_name = f"Solo_Team_{i + 1}"

        # Create solo team (all saved for solo)
        team_id = create_team(player, team_name, [player["username"]])

        if team_id:
            if register_team_to_tournament(solo_id, player, team_id, save_as_team=True):
                print(f"  ✅ Player {i + 1}/{len(solo_players_pool)} registered to Solo Tournament (Saved)")
                solo_teams.append({"name": team_name, "id": team_id, "saved": True})
                solo_players.append(player["email"])
            else:
                print(f"  ❌ Failed to register player {i + 1}")

    # Print summary
    print("\n" + "=" * 60)
    print("=== SUMMARY ===")
    print("=" * 60)
    print("\n🎮 Host Credentials:")
    print(f"   Email: {host_user['email']}")
    print("   Password: TestPass123!")

    print("\n🏆 Tournaments Created:")
    print(f"   - Squad: ID {squad_id} (10 teams, {len(squad_players)} players) [BASIC PLAN]")
    print("     • 7 permanent teams, 3 temporary teams")
    print(f"   - Duo: ID {duo_id} (10 teams, {len(duo_players)} players) [BASIC PLAN]")
    print("     • 8 permanent teams, 2 temporary teams")
    print(f"   - Solo: ID {solo_id} (10 teams, {len(solo_players)} players) [FEATURED PLAN]")
    print("     • All 10 teams permanent")
    print(f"   - Duo (Empty): ID {empty_duo_id} (No registrations) [FEATURED PLAN]")

    print(f"\n👥 Total Players Created: {len(all_players)}")
    print(f"\n   Squad Tournament ({len(squad_players)} players):")
    for i, p in enumerate(squad_players, 1):
        print(f"      {i}. {p}")

    print(f"\n   Duo Tournament ({len(duo_players)} players):")
    for i, p in enumerate(duo_players, 1):
        print(f"      {i}. {p}")

    print(f"\n   Solo Tournament ({len(solo_players)} players):")
    for i, p in enumerate(solo_players, 1):
        print(f"      {i}. {p}")

    print("\n   All player passwords: TestPass123!")

    print("\n📋 Team Summary:")
    print(f"   Total Permanent Teams: {sum(1 for t in squad_teams + duo_teams + solo_teams if t['saved'])}")
    print(f"   Total Temporary Teams: {sum(1 for t in squad_teams + duo_teams + solo_teams if not t['saved'])}")

    print("\n" + "=" * 60)
    print("✅ All tournaments, teams, and players created successfully!")
    print("=" * 60)
