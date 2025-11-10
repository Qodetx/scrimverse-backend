import random
import string

import requests

BASE_URL = "http://127.0.0.1:8000/api"


def random_email(prefix):
    return f"{prefix}_{''.join(random.choices(string.ascii_lowercase, k=5))}@test.com"


def register_host():
    url = f"{BASE_URL}/accounts/host/register/"
    data = {
        "email": random_email("host"),
        "username": "TestHost",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "organization_name": "TestHostOrg",
        "phone_number": "9999999999",
    }
    res = requests.post(url, json=data)
    print("DEBUG REGISTER HOST RESPONSE:", res.status_code, res.text)
    res = res.json()
    print("Host Registered:", res["user"]["email"])
    return res["tokens"]["access"], res["user"]


def create_tournament(token):
    url = f"{BASE_URL}/tournaments/create/"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "title": "Test Tournament",
        "game_name": "BGMI",
        "game_mode": "Squad",
        "max_participants": 10,
        "prize_pool": 10000,
        "entry_fee": 0,
        "rounds": [
            {"round": 1, "max_teams": 10, "qualifying_teams": 5},
            {"round": 2, "max_teams": 5, "qualifying_teams": 2},
            {"round": 3, "max_teams": 2, "qualifying_teams": 0},
        ],
    }
    res = requests.post(url, json=data, headers=headers).json()
    print("Tournament Created:", res["title"], "ID:", res["id"])
    return res["id"]


def register_player(tournament_id):
    player_email = random_email("player")
    url = f"{BASE_URL}/accounts/player/register/"
    data = {
        "email": player_email,
        "password": "TestPass123!",
        "in_game_name": f"Player_{random.randint(100, 999)}",
        "phone": "8888888888",
    }
    res = requests.post(url, json=data).json()
    player_token = res["tokens"]["access"]
    player_id = res["user"]["id"]

    register_url = f"{BASE_URL}/tournaments/{tournament_id}/register/"
    headers = {"Authorization": f"Bearer {player_token}"}
    reg_data = {
        "team_name": f"Team_{player_id}",
        "in_game_details": {"ign": f"IGN_{player_id}", "uid": f"UID_{player_id}", "rank": "Gold"},
    }
    requests.post(register_url, json=reg_data, headers=headers)
    print(f"Registered Player {player_email} to Tournament {tournament_id}")
    return player_email


if __name__ == "__main__":
    print("=== Automating Tournament Setup ===")
    host_token, host_user = register_host()
    tournament_id = create_tournament(host_token)

    players = []
    for _ in range(10):
        email = register_player(tournament_id)
        players.append(email)

    print("\n=== Summary ===")
    print(f"Host Email: {host_user['email']} | Password: TestPass123!")
    print("Players:")
    for p in players:
        print(f"  - {p} | Password: TestPass123!")

    print("\n✅ All players registered successfully!")
