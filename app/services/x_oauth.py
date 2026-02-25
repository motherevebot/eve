"""X/Twitter OAuth 2.0 PKCE flow — token exchange, profile fetch, tweet posting."""

import logging
import secrets

import httpx

from app.config import settings
from app.services.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.x.com/2/oauth2/token"
USER_ME_URL = "https://api.x.com/2/users/me"
TWEETS_URL = "https://api.x.com/2/tweets"


def generate_pkce() -> tuple[str, str]:
    """Generate code_verifier and code_challenge for PKCE (plain method for MVP)."""
    verifier = secrets.token_urlsafe(64)
    return verifier, verifier  # plain method


def build_authorize_url(state: str, code_challenge: str) -> str:
    return (
        "https://twitter.com/i/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={settings.x_client_id}"
        f"&redirect_uri={settings.x_redirect_uri}"
        f"&scope=tweet.read%20tweet.write%20users.read%20offline.access"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=plain"
    )


async def exchange_code(code: str, code_verifier: str) -> dict:
    """
    Exchange authorization code for access + refresh tokens.
    Returns {"access_token", "refresh_token", "expires_in", "token_type"}.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.x_redirect_uri,
                "code_verifier": code_verifier,
                "client_id": settings.x_client_id,
            },
            auth=(settings.x_client_id, settings.x_client_secret),
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token_enc: str) -> dict:
    """
    Use encrypted refresh token to get new access + refresh tokens.
    Returns new {"access_token", "refresh_token", ...}.
    """
    refresh_token = decrypt(refresh_token_enc)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.x_client_id,
            },
            auth=(settings.x_client_id, settings.x_client_secret),
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_profile(access_token: str) -> dict:
    """Fetch authenticated user's X profile."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            USER_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"user.fields": "id,name,username,profile_image_url"},
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("data", {})


async def post_tweet(access_token_enc: str, text: str) -> str | None:
    """
    Post a tweet using encrypted access token.
    Returns tweet_id on success, None on failure.
    """
    access_token = decrypt(access_token_enc)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TWEETS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"text": text},
        )
        if resp.status_code == 401:
            logger.warning("X token expired — needs refresh")
            return None
        if resp.status_code != 201:
            logger.error("Tweet post failed: %s %s", resp.status_code, resp.text[:300])
            return None

        data = resp.json()
    return data.get("data", {}).get("id")


def encrypt_tokens(access_token: str, refresh_token: str) -> tuple[str, str]:
    """Encrypt both tokens for DB storage."""
    return encrypt(access_token), encrypt(refresh_token)
