import requests
import json

url = "http://localhost:8000/api/accounts/login/"
data = {
    "email": "tester@scrimverse.com",
    "password": "Password123!",
    "user_type": "player"
}

try:
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
