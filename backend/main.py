"""FastAPI server: serves the website (docs/) and the API for accounts, picks, the leaderboard and Ask Joey.

Run it from the backend folder:   .venv/Scripts/python -m uvicorn main:app --port 8000
then open http://127.0.0.1:8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agents
import auth
import config
import db
import game
import leagues
import races
import safety

log = logging.getLogger("uvicorn.error")
COOKIE = "mt_session"
ask_per_user = safety.RateLimiter(config.ASK_PER_USER_PER_HOUR)
ask_per_ip = safety.RateLimiter(config.ASK_PER_IP_PER_HOUR)
signups_per_ip = safety.RateLimiter(10)
league_joins = safety.RateLimiter(10)   # join attempts per person per hour, so codes can't be guessed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    races.load()
    log.info("Midterm tracker ready: %d races, model %s, key %s", len(races.races()), config.MODEL_NAME,
             "found (" + str(config.env_file_used()) + ")" if config.env_file_used() else "MISSING")
    yield


app = FastAPI(title="2026 Midterm Tracker API", docs_url=None, redoc_url=None, lifespan=lifespan)


# ---------- helpers ----------

def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_user(request: Request) -> dict | None:
    return auth.user_for_session(request.cookies.get(COOKIE))


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Log in first.")
    return user


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """Block cross-site form/script posts: a write must come from this site (CSRF protection)."""
    if request.method in ("POST", "PUT", "DELETE") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            db.log_safety("cross_site_write", origin)
            return JSONResponse({"detail": "Cross-site requests aren't allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def set_session(response: Response, user_id: int) -> None:
    response.set_cookie(COOKIE, auth.create_session(user_id), max_age=auth.SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", secure=False, path="/")


# ---------- health ----------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model": config.MODEL_NAME, "key_found": bool(config.env_file_used()),
            "env_file": config.env_file_used(), "races": len(races.races()), "picks_closed": game.picks_closed()}


# ---------- accounts ----------

class Signup(BaseModel):
    nickname: str = Field(max_length=40)
    password: str = Field(max_length=200)
    avatar: str = Field(max_length=20)


class Login(BaseModel):
    nickname: str = Field(max_length=40)
    password: str = Field(max_length=200)


class AvatarIn(BaseModel):
    avatar: str = Field(max_length=20)


@app.post("/api/signup")
def signup(body: Signup, request: Request, response: Response) -> dict:
    if not signups_per_ip.allow(client_ip(request)):
        db.log_safety("signup_rate_limit", client_ip(request))
        raise HTTPException(429, "Too many new accounts from here. Try again later.")
    try:
        user = auth.create_user(body.nickname, body.password, body.avatar)
    except auth.AuthError as e:
        raise HTTPException(e.status, e.message)
    set_session(response, user["id"])
    return {"user": user}


@app.post("/api/login")
def login(body: Login, request: Request, response: Response) -> dict:
    key, ip = body.nickname.strip().lower(), client_ip(request)
    if auth.login_blocked(key, ip):
        db.log_safety("login_lockout", key[:24])
        raise HTTPException(429, "Too many wrong passwords. Wait 15 minutes and try again.")
    user = auth.authenticate(body.nickname, body.password)
    if not user:
        auth.record_failure(key, ip)
        raise HTTPException(401, "Wrong nickname or password.")
    auth.clear_failures(key)
    set_session(response, user["id"])
    return {"user": user}


@app.post("/api/logout")
def logout(request: Request, response: Response) -> dict:
    auth.delete_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request) -> dict:
    user = current_user(request)
    return {"user": user, "picks": game.get_picks(user["id"]) if user else {}}


@app.put("/api/me/avatar")
def change_avatar(body: AvatarIn, request: Request) -> dict:
    user = require_user(request)
    try:
        auth.set_avatar(user["id"], body.avatar)
    except auth.AuthError as e:
        raise HTTPException(e.status, e.message)
    return {"ok": True}


# ---------- game ----------

class PicksIn(BaseModel):
    picks: dict[str, str]


@app.put("/api/picks")
def put_picks(body: PicksIn, request: Request) -> dict:
    user = require_user(request)
    try:
        return {"picks": game.save_picks(user["id"], body.picks)}
    except game.GameError as e:
        raise HTTPException(e.status, e.message)


@app.get("/api/crowd")
def get_crowd() -> dict:
    return {"crowd": game.crowd()}


@app.get("/api/leaderboard")
def get_leaderboard() -> dict:
    return game.leaderboard()


# ---------- private leagues ----------

class LeagueIn(BaseModel):
    name: str = Field(max_length=60)


class JoinIn(BaseModel):
    code: str = Field(max_length=20)


def _league(call):
    try:
        return call()
    except leagues.LeagueError as e:
        raise HTTPException(e.status, e.message)


@app.get("/api/leagues")
def get_leagues(request: Request) -> dict:
    return {"leagues": leagues.my_leagues(require_user(request)["id"])}


@app.post("/api/leagues")
def make_league(body: LeagueIn, request: Request) -> dict:
    user = require_user(request)
    return {"league": _league(lambda: leagues.create(user["id"], body.name))}


@app.post("/api/leagues/join")
def join_league(body: JoinIn, request: Request) -> dict:
    user = require_user(request)
    if not league_joins.allow(f"u{user['id']}") or not league_joins.allow("ip" + client_ip(request)):
        db.log_safety("league_join_rate_limit", user["nickname"])
        raise HTTPException(429, "Too many tries. Wait a bit and check the code with your friend.")
    return {"league": _league(lambda: leagues.join(user["id"], body.code))}


@app.post("/api/leagues/{league_id}/leave")
def leave_league(league_id: int, request: Request) -> dict:
    user = require_user(request)
    _league(lambda: leagues.leave(user["id"], league_id))
    return {"ok": True}


@app.get("/api/leagues/{league_id}/leaderboard")
def league_leaderboard(league_id: int, request: Request) -> dict:
    user = require_user(request)
    return _league(lambda: leagues.leaderboard(user["id"], league_id))


# ---------- Ask Joey (the agents) ----------

class AskIn(BaseModel):
    question: str = Field(max_length=2000)


@app.post("/api/ask")
def ask(body: AskIn, request: Request) -> dict:
    user = require_user(request)
    if not ask_per_user.allow(f"u{user['id']}") or not ask_per_ip.allow(client_ip(request)):
        db.log_safety("ask_rate_limit", user["nickname"])
        raise HTTPException(429, f"That's a lot of questions! You can ask {config.ASK_PER_USER_PER_HOUR} per hour.")
    try:
        out = agents.ask(body.question)
    except Exception as e:  # a model or network failure shouldn't crash the page
        log.exception("ask failed")
        raise HTTPException(503, f"Joey couldn't answer right now ({type(e).__name__}). Try again in a minute.")
    return {k: out.get(k) for k in ("answer", "blocked", "race_ids", "trace", "cached")}


# ---------- the website itself ----------
app.mount("/", StaticFiles(directory=config.SITE_DIR, html=True), name="site")
