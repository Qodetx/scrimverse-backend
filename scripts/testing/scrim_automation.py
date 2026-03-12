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
        "email": random_email("scrimhost"),
        "username": f"ScrimHost_{random_suffix}",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "phone_number": "9999999999",
    }
    res = requests.post(url, json=data)
    res = res.json()
    print("Host Registered:", res["user"]["email"])
    return res["tokens"]["access"], res["user"]


def create_scrim(token, game_mode, max_teams, max_matches=4, prize_pool=5000):
    """Create a scrim with specified parameters"""
    url = f"{BASE_URL}/tournaments/create/"
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now()

    # Prepare form data for scrim
    data = {
        "title": f"Practice Scrim - {game_mode} - {max_teams} Teams",
        "description": f"Practice scrim session for {game_mode} mode with {max_teams} teams and {max_matches} matches.",
        "rules": "1. Practice mode - no toxic behavior\n2. Focus on improvement\n3. Respect all players\n4. Have fun!",
        "game_name": "BGMI",
        "game_mode": game_mode,
        "max_participants": max_teams,
        "prize_pool": prize_pool,
        "entry_fee": 0,
        "max_matches": max_matches,
        "event_mode": "SCRIM",  # Important: Mark as SCRIM
        "registration_start": now.isoformat(),
        "registration_end": (now + timedelta(hours=6)).isoformat(),
        "tournament_start": (now + timedelta(hours=8)).isoformat(),
        "tournament_end": (now + timedelta(hours=12)).isoformat(),
        "plan_type": "basic",
        "rounds": [
            {
                "round": 1,
                "max_teams": max_teams,
                "qualifying_teams": 0,  # Scrims don't have qualification
            }
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
    print(
        f"Scrim Created: {res['title']} | ID: {res['id']} | Mode: {game_mode} | Max Teams: {max_teams} | Matches: {max_matches}"  # noqa: E501
    )
    return res["id"]


def create_player():
    """Create a single player with meaningful name and return their credentials"""
    player_email = random_email("scrimplayer")
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


def register_team_to_scrim(scrim_id, captain_player, team_id, save_as_team=True):
    """Register an existing team to a scrim"""
    register_url = f"{BASE_URL}/tournaments/{scrim_id}/register/"
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
    print("=== SCRIM AUTOMATION (25 Teams from 30, 120 Players) ===")
    print("=" * 80)

    # Register host
    print("\n--- Registering Host ---")
    host_token, host_user = register_host()

    # Create scrim for 25 teams with 4 matches
    print("\n--- Creating Scrim ---")
    scrim_id = create_scrim(host_token, "Squad", 25, max_matches=4, prize_pool=5000)

    # Create 120 players (30 teams × 4 players)
    print("\n--- Creating 120 Players (for 30 teams) ---")
    all_players = []
    for i in range(120):
        player = create_player()
        if player:
            all_players.append(player)
            if (i + 1) % 20 == 0:  # Print progress every 20 players
                print(f"  Progress: {i + 1}/120 players created...")

    print(f"\n✅ Created {len(all_players)} players successfully!")

    # Create 30 teams but only register 25 to the scrim
    print("\n--- Creating 30 Teams (Registering 25 to Scrim) ---")
    all_teams = []
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

        # Create team (all teams saved)
        team_id = create_team(captain, team_name, member_usernames)

        if team_id:
            team_info = {
                "number": team_num + 1,
                "name": team_name,
                "id": team_id,
                "captain": captain["username"],
                "members": member_usernames,
                "registered": False,
            }
            all_teams.append(team_info)

            # Only register first 25 teams to scrim
            if team_num < 25:
                if register_team_to_scrim(scrim_id, captain, team_id, save_as_team=True):
                    team_info["registered"] = True
                    registered_teams.append(team_info)

                    # Print progress every 5 teams
                    if (team_num + 1) % 5 == 0:
                        print(f"  Progress: {team_num + 1}/25 teams registered to scrim...")
                else:
                    failed_teams += 1
            else:
                print(f"  ℹ️ Team {team_num + 1} created but not registered (reserve team)")
        else:
            failed_teams += 1

    # Print summary
    print("\n" + "=" * 80)
    print("=== SUMMARY ===")
    print("=" * 80)

    print("\n🎮 Host Credentials:")
    print(f"   Email: {host_user['email']}")
    print("   Password: TestPass123!")

    print("\n🏆 Scrim Created:")
    print("   - Title: Practice Scrim - Squad - 25 Teams")
    print(f"   - ID: {scrim_id}")
    print("   - Mode: Squad")
    print("   - Event Type: SCRIM")
    print("   - Max Teams: 25")
    print("   - Max Matches: 4")
    print("   - Prize Pool: ₹5,000")
    print(f"   - Total Players Created: {len(all_players)}")

    print("\n👥 Team Creation Results:")
    print(f"   - Total Teams Created: {len(all_teams)}")
    print(f"   - Registered to Scrim: {len(registered_teams)}")
    print(f"   - Reserve Teams (not registered): {len(all_teams) - len(registered_teams)}")
    print(f"   - Failed: {failed_teams}")

    print("\n📋 Registered Teams (25):")
    for team in registered_teams:
        print(f"   {team['number']}. {team['name']} - Captain: {team['captain']} [✅ Registered]")

    print("\n📋 Reserve Teams (5):")
    reserve_teams = [t for t in all_teams if not t["registered"]]
    for team in reserve_teams:
        print(f"   {team['number']}. {team['name']} - Captain: {team['captain']} [⏸️ Not Registered]")

    print("\n💡 Player Credentials:")
    print("   All players have password: TestPass123!")
    print("   Sample player emails:")
    for i in range(min(5, len(all_players))):
        print(f"      - {all_players[i]['email']} (Username: {all_players[i]['username']})")

    print("\n📊 Scrim Details:")
    print("   - 1 Round (no qualification)")
    print("   - 1 Group (all teams together)")
    print("   - 4 Matches maximum")
    print("   - Aggregate points determine winner")
    print("   - Practice mode - focus on improvement!")

    print("\n" + "=" * 80)
    print("✅ Scrim setup complete!")
    print("=" * 80)
