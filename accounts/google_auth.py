"""
Google OAuth Authentication Utilities
"""
import requests as http_requests

from decouple import config
from google.auth.transport import requests
from google.oauth2 import id_token


class GoogleOAuth:
    """Helper class for Google OAuth operations"""

    @staticmethod
    def verify_google_token(token):
        """
        Verify Google OAuth token (id_token or access_token) and return user info.
        Tries id_token verification first, falls back to access_token userinfo endpoint.
        """
        # Try id_token verification first
        try:
            client_id = config("GOOGLE_CLIENT_ID")
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)

            if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
                raise ValueError("Wrong issuer.")

            return {
                "email": idinfo.get("email"),
                "email_verified": idinfo.get("email_verified", False),
                "name": idinfo.get("name"),
                "picture": idinfo.get("picture"),
                "given_name": idinfo.get("given_name"),
                "family_name": idinfo.get("family_name"),
                "google_id": idinfo.get("sub"),
            }
        except ValueError:
            pass

        # Fall back to access_token userinfo endpoint
        try:
            response = http_requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code != 200:
                raise ValueError("Invalid access token")

            info = response.json()
            return {
                "email": info.get("email"),
                "email_verified": info.get("email_verified", False),
                "name": info.get("name"),
                "picture": info.get("picture"),
                "given_name": info.get("given_name"),
                "family_name": info.get("family_name"),
                "google_id": info.get("sub"),
            }
        except Exception as e:
            raise ValueError(f"Invalid Google token: {str(e)}")
