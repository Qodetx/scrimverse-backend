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
        "organization_name": f"TestHostOrg_{random_suffix}",
        "phone_number": "9999999999",
    }
    res = requests.post(url, json=data)
    res = res.json()
    print("Host Registered:", res["user"]["email"])
    return res["tokens"]["access"], res["user"]


def create_tournament(token, game_mode, max_teams, title_suffix=""):
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
            import json

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
        "in_game_name": f"IGN_{unique_id}",
        "phone_number": "8888888888",
        "game_id": "BGMI",
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


def register_team_to_tournament(tournament_id, team_players, team_name, game_mode):
    """Register a team (or solo player) to a tournament"""
    if not team_players:
        return False

    # Use first player's token to register the team
    register_url = f"{BASE_URL}/tournaments/{tournament_id}/register/"
    headers = {"Authorization": f"Bearer {team_players[0]['token']}"}

    reg_data = {
        "team_name": team_name,
        "player_usernames": [p["username"] for p in team_players],
        "in_game_details": {
            "ign": f"IGN_{team_players[0]['unique_id']}",
            "uid": f"UID_{team_players[0]['id']}",
            "rank": "Gold",
        },
    }

    reg_response = requests.post(register_url, json=reg_data, headers=headers)
    if reg_response.status_code == 201:
        return True
    else:
        print(f"ERROR: Failed to register team: {reg_response.text}")
        return False


if __name__ == "__main__":
    print("=== Automating Tournament Setup ===\n")

    # Register host
    host_token, host_user = register_host()
    print()

    # Create tournaments
    print("\n--- Creating Tournaments ---")
    squad_id = create_tournament(host_token, "Squad", 10)  # 10 teams
    duo_id = create_tournament(host_token, "Duo", 10)  # 10 teams
    solo_id = create_tournament(host_token, "Solo", 10)  # 10 teams
    empty_duo_id = create_tournament(host_token, "Duo", 10, " (Empty)")  # 10 teams

    # Create 40 players upfront
    print("\n--- Creating 40 Players ---")
    all_players = []
    for i in range(40):
        player = create_player()
        if player:
            all_players.append(player)
            print(f"  Created player {i+1}/40: {player['email']}")

    print(f"\n✅ Created {len(all_players)} players successfully!")

    # Register all 40 players to Squad tournament (10 teams of 4)
    print("\n--- Registering 10 teams for Squad Tournament ---")
    squad_players = []
    for team_num in range(10):
        team_players = all_players[team_num * 4 : (team_num + 1) * 4]
        team_name = f"Squad_Team_{team_num + 1}"

        if register_team_to_tournament(squad_id, team_players, team_name, "Squad"):
            print(f"  ✅ Team {team_num + 1}/10 registered ({len(team_players)} players)")
            squad_players.extend([p["email"] for p in team_players])
        else:
            print(f"  ❌ Failed to register Team {team_num + 1}")

    # Register random 20 players to Duo tournament (10 teams of 2)
    print("\n--- Registering 10 teams for Duo Tournament ---")
    duo_players_pool = random.sample(all_players, 20)  # Random 20 players
    duo_players = []
    for team_num in range(10):
        team_players = duo_players_pool[team_num * 2 : (team_num + 1) * 2]
        team_name = f"Duo_Team_{team_num + 1}"

        if register_team_to_tournament(duo_id, team_players, team_name, "Duo"):
            print(f"  ✅ Team {team_num + 1}/10 registered ({len(team_players)} players)")
            duo_players.extend([p["email"] for p in team_players])
        else:
            print(f"  ❌ Failed to register Team {team_num + 1}")

    # Register 10 players to Solo tournament (10 teams of 1)
    print("\n--- Registering 10 players for Solo Tournament ---")
    solo_players_pool = all_players[:10]  # First 10 players
    solo_players = []
    for i, player in enumerate(solo_players_pool):
        team_name = f"Solo_Team_{i + 1}"

        if register_team_to_tournament(solo_id, [player], team_name, "Solo"):
            print(f"  ✅ Player {i + 1}/10 registered")
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
    print(f"   - Squad: ID {squad_id} (10 teams, {len(squad_players)} players)")
    print(f"   - Duo: ID {duo_id} (10 teams, {len(duo_players)} players)")
    print(f"   - Solo: ID {solo_id} (10 teams, {len(solo_players)} players)")
    print(f"   - Duo (Empty): ID {empty_duo_id} (No registrations)")

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

    print("\n" + "=" * 60)
    print("✅ All tournaments and players created successfully!")
    print("=" * 60)
