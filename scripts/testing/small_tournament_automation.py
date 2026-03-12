import json
import random
import string
from datetime import datetime, timedelta

import requests

BASE_URL = "http://127.0.0.1:8000/api"
BANNER_IMAGE_PATH = "/Users/Sukruth30/Downloads/download.jpeg"

# Meaningful team name components
TEAM_PREFIXES = [
    "Alpha",
    "Beta",
    "Gamma",
    "Delta",
    "Omega",
    "Sigma",
    "Phoenix",
    "Dragon",
    "Tiger",
    "Wolf",
    "Eagle",
    "Falcon",
    "Hawk",
    "Raven",
    "Viper",
    "Cobra",
    "Panther",
    "Lion",
    "Bear",
    "Shark",
    "Thunder",
    "Lightning",
    "Storm",
    "Blaze",
    "Inferno",
    "Frost",
    "Ice",
    "Shadow",
    "Ghost",
    "Phantom",
]

TEAM_SUFFIXES = [
    "Squad",
    "Force",
    "Legion",
    "Battalion",
    "Crew",
    "Gang",
    "Clan",
    "Guild",
    "Alliance",
    "Warriors",
    "Fighters",
    "Hunters",
    "Slayers",
    "Guardians",
    "Defenders",
    "Champions",
    "Heroes",
    "Legends",
    "Elites",
    "Strikers",
    "Raiders",
    "Invaders",
    "Conquerors",
    "Dominators",
    "Phantoms",
    "Blazers",
    "Storms",
    "Aces",
]

PLAYER_FIRST_NAMES = [
    "Shadow",
    "Blaze",
    "Storm",
    "Frost",
    "Venom",
    "Titan",
    "Phoenix",
    "Dragon",
    "Wolf",
    "Eagle",
    "Ghost",
    "Phantom",
    "Viper",
    "Cobra",
    "Thunder",
    "Lightning",
    "Nova",
    "Nebula",
    "Cosmic",
    "Quantum",
    "Steel",
    "Iron",
    "Chrome",
    "Silver",
    "Gold",
    "Cyber",
    "Neon",
    "Pulse",
    "Volt",
    "Surge",
    "Apex",
    "Elite",
    "Prime",
    "Supreme",
    "Legendary",
    "Mythic",
    "Epic",
    "Heroic",
    "Divine",
    "Sacred",
]

PLAYER_LAST_NAMES = [
    "Killer",
    "Slayer",
    "Hunter",
    "Reaper",
    "Destroyer",
    "Master",
    "Lord",
    "King",
    "Champion",
    "Legend",
    "Warrior",
    "Fighter",
    "Soldier",
    "Shadow",
    "Ghost",
    "Phantom",
    "Storm",
    "Thunder",
    "Lightning",
    "Blaze",
    "Steel",
    "Iron",
    "Wolf",
    "Lion",
    "Tiger",
    "Eagle",
    "Striker",
    "Raider",
    "Ace",
    "Pro",
]


def random_email(prefix):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase, k=5))}@test.com"


def generate_team_name():
    """Generate a meaningful team name"""
    prefix = random.choice(TEAM_PREFIXES)
    suffix = random.choice(TEAM_SUFFIXES)
    return f"{prefix} {suffix}"


def generate_player_name():
    """Generate a meaningful player username"""
    first = random.choice(PLAYER_FIRST_NAMES)
    last = random.choice(PLAYER_LAST_NAMES)
    number = random.randint(1, 999)
    return f"{first}{last}{number}"


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
    data = {
        "title": f"Test Tournament - {game_mode}{title_suffix}",
        "description": f"Small test tournament for {game_mode} mode with {max_teams} teams.",
        "rules": "1. Play fair\n2. No hacks\n3. Respect opponents\n4. Follow tournament schedule",
        "game_name": "BGMI",
        "game_mode": game_mode,
        "max_participants": max_teams,
        "prize_pool": 10000,
        "entry_fee": 0,
        "registration_start": now.isoformat(),
        "registration_end": (now + timedelta(hours=12)).isoformat(),
        "tournament_start": (now + timedelta(days=1)).isoformat(),
        "tournament_end": (now + timedelta(days=2)).isoformat(),
        "plan_type": plan_type,
        "rounds": [
            {"round": 1, "max_teams": max_teams, "qualifying_teams": 16},
            {"round": 2, "max_teams": 16, "qualifying_teams": 8},
            {"round": 3, "max_teams": 8, "qualifying_teams": 0},
        ],
    }

    # Prepare multipart form data with banner image
    files = {}
    try:
        with open(BANNER_IMAGE_PATH, "rb") as img:
            files = {"banner_image": ("download.jpeg", img, "image/jpeg")}
            form_data = data.copy()
            form_data["rounds"] = json.dumps(data["rounds"])

            res = requests.post(url, data=form_data, files=files, headers=headers)
    except FileNotFoundError:
        print(f"Warning: Banner image not found at {BANNER_IMAGE_PATH}, creating without banner")
        res = requests.post(url, json=data, headers=headers)

    res = res.json()
    print(f"Tournament Created: {res['title']} | ID: {res['id']} | Mode: {game_mode} | Max Teams: {max_teams}")
    return res["id"]


def create_player():
    """Create a single player with meaningful name and return their credentials"""
    player_email = random_email("player")
    url = f"{BASE_URL}/accounts/player/register/"
    username = generate_player_name()

    data = {
        "email": player_email,
        "username": username,
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
    }


def create_team(captain_player, team_name, member_usernames):
    """Create a team with the captain and members"""
    url = f"{BASE_URL}/accounts/teams/"
    headers = {"Authorization": f"Bearer {captain_player['token']}"}

    data = {
        "name": team_name,
        "player_usernames": member_usernames,
    }

    res = requests.post(url, json=data, headers=headers)

    if res.status_code == 201:
        team_data = res.json()
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
        "save_as_team": save_as_team,
    }

    reg_response = requests.post(register_url, json=reg_data, headers=headers)
    if reg_response.status_code == 201:
        return True
    else:
        print(f"  ❌ Failed to register team: {reg_response.text}")
        return False


if __name__ == "__main__":
    print("=" * 80)
    print("=== SMALL TOURNAMENT AUTOMATION (30 Teams, 120 Players) ===")
    print("=" * 80)

    # Register host
    print("\n--- Registering Host ---")
    host_token, host_user = register_host()

    # Create tournament for 30 teams
    print("\n--- Creating Tournament ---")
    squad_id = create_tournament(host_token, "Squad", 30, " - 30 Teams", plan_type="basic")

    # Create 120 players (30 teams × 4 players)
    print("\n--- Creating 120 Players ---")
    all_players = []
    for i in range(120):
        player = create_player()
        if player:
            all_players.append(player)
            if (i + 1) % 20 == 0:  # Print progress every 20 players
                print(f"  Progress: {i + 1}/120 players created...")

    print(f"\n✅ Created {len(all_players)} players successfully!")

    # Create 30 teams and register them
    print("\n--- Creating 30 Teams and Registering to Tournament ---")
    registered_teams = []
    failed_teams = 0

    for team_num in range(30):
        # Get 4 players for this team
        team_players = all_players[team_num * 4 : (team_num + 1) * 4]

        if len(team_players) < 4:
            print(f"  ⚠️ Not enough players for team {team_num + 1}")
            break

        captain = team_players[0]
        team_name = generate_team_name()

        # Get all usernames including captain
        member_usernames = [p["username"] for p in team_players]

        # Create team (first 25 teams saved, last 5 temporary)
        team_id = create_team(captain, team_name, member_usernames)

        if team_id:
            # Register to tournament
            save_team = team_num < 25  # First 25 saved, last 5 temporary
            if register_team_to_tournament(squad_id, captain, team_id, save_as_team=save_team):
                registered_teams.append(
                    {
                        "number": team_num + 1,
                        "name": team_name,
                        "id": team_id,
                        "saved": save_team,
                        "captain": captain["username"],
                        "members": member_usernames,
                    }
                )

                # Print progress every 5 teams
                if (team_num + 1) % 5 == 0:
                    print(f"  Progress: {team_num + 1}/30 teams registered...")
            else:
                failed_teams += 1
        else:
            failed_teams += 1

    # Print summary
    print("\n" + "=" * 80)
    print("=== SUMMARY ===")
    print("=" * 80)

    print("\n🎮 Host Credentials:")
    print(f"   Email: {host_user['email']}")
    print("   Password: TestPass123!")

    print("\n🏆 Tournament Created:")
    print("   - Title: Test Tournament - Squad - 30 Teams")
    print(f"   - ID: {squad_id}")
    print("   - Mode: Squad")
    print("   - Plan: BASIC")
    print("   - Max Teams: 30")
    print(f"   - Total Players: {len(all_players)}")

    print("\n👥 Registration Results:")
    print(f"   - Successfully Registered: {len(registered_teams)} teams")
    print(f"   - Failed: {failed_teams} teams")
    print(f"   - Permanent Teams: {sum(1 for t in registered_teams if t['saved'])}")
    print(f"   - Temporary Teams: {sum(1 for t in registered_teams if not t['saved'])}")

    print("\n📋 All Registered Teams:")
    for team in registered_teams:
        status = "✅ Saved" if team["saved"] else "⏳ Temp"
        print(f"   {team['number']}. {team['name']} - Captain: {team['captain']} [{status}]")

    print("\n💡 Player Credentials:")
    print("   All players have password: TestPass123!")
    print("   Sample player emails:")
    for i in range(min(5, len(all_players))):
        print(f"      - {all_players[i]['email']} (Username: {all_players[i]['username']})")

    print("\n" + "=" * 80)
    print("✅ Small tournament setup complete!")
    print("=" * 80)
