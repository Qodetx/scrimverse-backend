"""
Tests for Google OAuth authentication
"""
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from accounts.google_auth import GoogleOAuth
from accounts.models import PlayerProfile, User
from tests.factories import UserFactory


@pytest.mark.django_db
def test_verify_google_token_success():
    """Test Google token verification with successful response"""
    mock_idinfo = {
        "iss": "https://accounts.google.com",
        "email": "test@gmail.com",
        "email_verified": True,
        "name": "Test User",
        "picture": "https://example.com/pic.jpg",
        "given_name": "Test",
        "family_name": "User",
        "sub": "123456789",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = mock_idinfo

        result = GoogleOAuth.verify_google_token("fake-token")

        assert result["email"] == "test@gmail.com"
        assert result["google_id"] == "123456789"
        assert result["email_verified"] is True


@pytest.mark.django_db
def test_verify_google_token_wrong_issuer():
    """Test failure when issuer is incorrect"""
    mock_idinfo = {
        "iss": "wrong-issuer.com",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = mock_idinfo

        with pytest.raises(ValueError, match="Invalid Google token: Wrong issuer."):
            GoogleOAuth.verify_google_token("fake-token")


@pytest.mark.django_db
def test_verify_google_token_invalid():
    """Test failure when token is invalid"""
    with patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.side_effect = ValueError("Token expired")

        with pytest.raises(ValueError, match="Invalid Google token: Token expired"):
            GoogleOAuth.verify_google_token("fake-token")


@pytest.mark.django_db
def test_google_auth_view_login_success():
    """Test successful login via GoogleAuthView"""
    client = APIClient()
    user = UserFactory(email="existing@test.com", user_type="player")
    PlayerProfile.objects.create(user=user)

    mock_info = {
        "email": "existing@test.com",
        "email_verified": True,
        "sub": "12345",
    }

    with patch("accounts.google_auth.GoogleOAuth.verify_google_token") as mock_verify:
        mock_verify.return_value = mock_info

        data = {"token": "valid-token", "user_type": "player", "is_signup": False}
        response = client.post("/api/accounts/google-auth/", data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["email"] == "existing@test.com"
        assert "tokens" in response.data


@pytest.mark.django_db
def test_google_auth_view_signup_success():
    """Test successful signup via GoogleAuthView"""
    client = APIClient()
    email = "newuser@test.com"

    mock_info = {
        "email": email,
        "email_verified": True,
        "sub": "12345",
    }

    with patch("accounts.google_auth.GoogleOAuth.verify_google_token") as mock_verify:
        mock_verify.return_value = mock_info

        data = {
            "token": "valid-token",
            "user_type": "player",
            "is_signup": True,
            "username": "newplayer",
            "phone_number": "1234567890",
        }
        response = client.post("/api/accounts/google-auth/", data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Account created successfully!"

        # Verify user and profile created
        user = User.objects.get(email=email)
        assert user.username == "newplayer"
        assert PlayerProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_google_auth_view_wrong_user_type_error():
    """Test error when user type doesn't match existing account"""
    client = APIClient()
    user = UserFactory(email="player@test.com", user_type="player")
    PlayerProfile.objects.create(user=user)

    mock_info = {
        "email": "player@test.com",
        "email_verified": True,
        "sub": "12345",
    }

    with patch("accounts.google_auth.GoogleOAuth.verify_google_token") as mock_verify:
        mock_verify.return_value = mock_info

        data = {"token": "valid-token", "user_type": "host", "is_signup": False}  # existing is player
        response = client.post("/api/accounts/google-auth/", data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already registered as a player" in response.data["error"]


@pytest.mark.django_db
def test_google_auth_view_missing_token():
    """Test error when token is missing"""
    client = APIClient()
    data = {"user_type": "player"}
    response = client.post("/api/accounts/google-auth/", data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Google token is required" in response.data["error"]
