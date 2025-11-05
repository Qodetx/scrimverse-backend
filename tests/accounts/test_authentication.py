"""
Test cases for authentication (register, login)
"""
from django.contrib.auth import get_user_model

import pytest
from rest_framework import status

User = get_user_model()


# Player Registration Tests


@pytest.mark.auth
@pytest.mark.django_db
def test_player_registration_success(api_client):
    """Test successful player registration"""
    data = {
        "email": "newplayer@test.com",
        "username": "newplayer",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "phone_number": "9876543210",
        "in_game_name": "ProGamer",
        "game_id": "UID123456",
    }
    response = api_client.post("/api/accounts/player/register/", data)

    assert response.status_code == status.HTTP_201_CREATED
    assert "tokens" in response.data
    assert "access" in response.data["tokens"]
    assert "refresh" in response.data["tokens"]
    assert User.objects.filter(email="newplayer@test.com").exists()

    user = User.objects.get(email="newplayer@test.com")
    assert user.user_type == "player"
    assert hasattr(user, "player_profile")
    assert user.player_profile.in_game_name == "ProGamer"


@pytest.mark.auth
@pytest.mark.django_db
def test_player_registration_password_mismatch(api_client):
    """Test registration fails when passwords don't match"""
    data = {
        "email": "player@test.com",
        "username": "player",
        "password": "TestPass123!",
        "password2": "DifferentPass123!",
        "phone_number": "9876543210",
        "in_game_name": "Gamer",
        "game_id": "UID123",
    }
    response = api_client.post("/api/accounts/player/register/", data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not User.objects.filter(email="player@test.com").exists()


@pytest.mark.auth
@pytest.mark.django_db
def test_player_registration_duplicate_email(api_client, player_user):
    """Test registration fails with duplicate email"""
    data = {
        "email": player_user.email,
        "username": "newusername",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "phone_number": "9876543210",
        "in_game_name": "Gamer",
        "game_id": "UID123",
    }
    response = api_client.post("/api/accounts/player/register/", data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.auth
@pytest.mark.django_db
def test_player_registration_missing_fields(api_client):
    """Test registration fails with missing required fields"""
    data = {
        "email": "incomplete@test.com",
        "password": "TestPass123!",
    }
    response = api_client.post("/api/accounts/player/register/", data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# Host Registration Tests


@pytest.mark.auth
@pytest.mark.django_db
def test_host_registration_success(api_client):
    """Test successful host registration"""
    data = {
        "email": "newhost@test.com",
        "username": "newhost",
        "password": "TestPass123!",
        "password2": "TestPass123!",
        "phone_number": "9876543210",
        "organization_name": "Gaming Org",
    }
    response = api_client.post("/api/accounts/host/register/", data)

    assert response.status_code == status.HTTP_201_CREATED
    assert "tokens" in response.data
    assert "access" in response.data["tokens"]
    assert "refresh" in response.data["tokens"]

    user = User.objects.get(email="newhost@test.com")
    assert user.user_type == "host"
    assert hasattr(user, "host_profile")
    assert user.host_profile.organization_name == "Gaming Org"


@pytest.mark.auth
@pytest.mark.django_db
def test_host_registration_password_mismatch(api_client):
    """Test host registration fails with password mismatch"""
    data = {
        "email": "host@test.com",
        "username": "host",
        "password": "TestPass123!",
        "password2": "Wrong123!",
        "phone_number": "9876543210",
        "organization_name": "Org",
    }
    response = api_client.post("/api/accounts/host/register/", data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# Login Tests


@pytest.mark.auth
@pytest.mark.django_db
def test_player_login_success(api_client, player_user):
    """Test successful player login"""
    data = {"email": player_user.email, "password": "testpass123", "user_type": "player"}
    response = api_client.post("/api/accounts/login/", data)

    assert response.status_code == status.HTTP_200_OK
    assert "tokens" in response.data
    assert "access" in response.data["tokens"]
    assert "refresh" in response.data["tokens"]
    assert response.data["user"]["email"] == player_user.email


@pytest.mark.auth
@pytest.mark.django_db
def test_host_login_success(api_client, host_user):
    """Test successful host login"""
    data = {"email": host_user.email, "password": "testpass123", "user_type": "host"}
    response = api_client.post("/api/accounts/login/", data)

    assert response.status_code == status.HTTP_200_OK
    assert "tokens" in response.data
    assert "access" in response.data["tokens"]
    assert response.data["user"]["user_type"] == "host"


@pytest.mark.auth
@pytest.mark.django_db
def test_login_wrong_password(api_client, player_user):
    """Test login fails with wrong password"""
    data = {"email": player_user.email, "password": "wrongpassword", "user_type": "player"}
    response = api_client.post("/api/accounts/login/", data)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.auth
@pytest.mark.django_db
def test_login_wrong_user_type(api_client, player_user):
    """Test login fails with wrong user type"""
    data = {"email": player_user.email, "password": "testpass123", "user_type": "host"}
    response = api_client.post("/api/accounts/login/", data)

    # Returns 403 when user type doesn't match
    assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]


@pytest.mark.auth
@pytest.mark.django_db
def test_login_nonexistent_user(api_client):
    """Test login fails for non-existent user"""
    data = {"email": "nonexistent@test.com", "password": "somepassword", "user_type": "player"}
    response = api_client.post("/api/accounts/login/", data)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.auth
@pytest.mark.django_db
def test_login_missing_fields(api_client):
    """Test login fails with missing fields"""
    data = {"email": "user@test.com"}
    response = api_client.post("/api/accounts/login/", data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# Get Current User Tests


@pytest.mark.auth
@pytest.mark.django_db
def test_get_current_user_player(authenticated_client, player_user):
    """Test getting current player user"""
    response = authenticated_client.get("/api/accounts/me/")

    assert response.status_code == status.HTTP_200_OK
    assert "user" in response.data or "email" in response.data
    # Check if response is direct user data or wrapped
    user_data = response.data if "email" in response.data else response.data.get("user", {})
    assert user_data.get("email") == player_user.email


@pytest.mark.auth
@pytest.mark.django_db
def test_get_current_user_host(host_authenticated_client, host_user):
    """Test getting current host user"""
    response = host_authenticated_client.get("/api/accounts/me/")

    assert response.status_code == status.HTTP_200_OK
    assert "user" in response.data or "email" in response.data
    user_data = response.data if "email" in response.data else response.data.get("user", {})
    assert user_data.get("email") == host_user.email


@pytest.mark.auth
@pytest.mark.django_db
def test_get_current_user_unauthenticated(api_client):
    """Test getting current user without authentication"""
    response = api_client.get("/api/accounts/me/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
