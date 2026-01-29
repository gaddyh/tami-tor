# google_calendar/oauth.py

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi import Response, Form
from google_auth_oauthlib.flow import Flow
import os, re

from adapters.google.tokens import (
    save_token_for_user,
    save_auth_state,
    load_user_id_from_state,
    delete_auth_state,
)

# ---- Router ----
google_router = APIRouter()

# ---- Config ----

from dotenv import load_dotenv
load_dotenv(".venv/.env")
secrets_dir = os.getenv("SECRETS_DIR", "/etc/secrets/")
CLIENT_SECRET_FILE = os.path.join(secrets_dir, "client_secret.json")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
]
#REDIRECT_URI = "https://whatsmatter-platform.onrender.com/google/oauth2callback"
REDIRECT_URI = "https://tami-web-tdl1.onrender.com/google/oauth2callback"

def phone_to_user_id(phone: str) -> str:
    return phone

def normalize_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")
    if not digits.startswith("972"):
        if digits.startswith("0") and len(digits) >= 10:
            digits = "972" + digits[1:]
    if not re.fullmatch(r"9725\d{7,8}", digits):
        raise ValueError("invalid phone")
    return digits

# ---- Auth endpoints ----
@google_router.post("/google/connect")
async def google_connect_submit(
    request: Request,
    response: Response,
    phone: str = Form(...),
):
    try:
        phone_norm = normalize_phone(phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid phone. Use format like 9725XXXXXXXX.")

    user_id = phone_to_user_id(phone_norm)

    # Build OAuth flow
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Google OAuth client_secret.json not found")

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    save_auth_state(state, user_id)

    # Redirect to Google; also set short-lived state cookie (defense-in-depth)
    redirect = RedirectResponse(url=auth_url, status_code=302)
    redirect.set_cookie(
        "g_state", state, httponly=True, secure=True, samesite="lax", max_age=600
    )
    return redirect

@google_router.get("/google/auth-url")
async def google_auth_url(user_id: str):
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Google OAuth client_secret.json not found")

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    save_auth_state(state, user_id)
    return {"auth_url": auth_url}

@google_router.get("/google/oauth2callback")
async def oauth2callback(request: Request):
    state = request.query_params.get("state")
    code = request.query_params.get("code")

    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code")

    user_id = load_user_id_from_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_FILE, scopes=SCOPES, state=state, redirect_uri=REDIRECT_URI
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Google OAuth client_secret.json not found")

    # Exchange code → tokens
    flow.fetch_token(code=code)
    credentials = flow.credentials

    save_token_for_user(user_id, credentials)
    delete_auth_state(state)

    return RedirectResponse(url="/success", status_code=302)
