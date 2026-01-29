# google_calendar/tokens.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import RefreshError

from db.session import SessionLocal
from models.session import Session
from models.google_oauth import GoogleToken, GoogleAuthState


def get_valid_credentials(user_id: str) -> Optional[Credentials]:
    creds = load_token_for_user(user_id)
    if creds is None:
        return None

    try:
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            save_token_for_user(user_id, creds)  # Persist the new token
        return creds
    except RefreshError:
        print(f"⚠️ Refresh failed for user: {user_id}")
        return None


def save_token_for_user(user_id: str, credentials: Credentials) -> None:
    session = SessionLocal()

    # Normalize scopes
    scopes = credentials.scopes or []
    scopes_str = " ".join(scopes)

    row = session.get(GoogleToken, user_id)
    if row is None:
        row = GoogleToken(user_id=user_id)

    row.token = credentials.token
    row.refresh_token = credentials.refresh_token
    row.token_uri = credentials.token_uri
    row.client_id = credentials.client_id
    row.client_secret = credentials.client_secret
    row.scopes = scopes_str
    row.expiry = credentials.expiry  # datetime or None

    session.add(row)
    session.commit()


def load_token_for_user(user_id: str) -> Optional[Credentials]:
    session = SessionLocal()
    row = session.get(GoogleToken, user_id)

    if row is None:
        print(f"⚠️ No token found for user: {user_id}")
        return None

    scopes = row.scopes.split() if row.scopes else None

    return Credentials(
        token=row.token,
        refresh_token=row.refresh_token,
        token_uri=row.token_uri,
        client_id=row.client_id,
        client_secret=row.client_secret,
        scopes=scopes,
        expiry=row.expiry,
    )


def save_auth_state(state: str, user_id: str) -> None:
    session = SessionLocal()
    row = GoogleAuthState(state=state, user_id=user_id)
    session.add(row)
    session.commit()


def load_user_id_from_state(state: str) -> Optional[str]:
    session = SessionLocal()
    row = session.get(GoogleAuthState, state)

    if row is None:
        print(f"⚠️ No state found for state: {state}")
        return None

    return row.user_id


def delete_auth_state(state: str) -> None:
    session = SessionLocal()
    row = session.get(GoogleAuthState, state)
    if row is None:
        return
    session.delete(row)
    session.commit()
