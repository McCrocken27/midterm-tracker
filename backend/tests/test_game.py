"""Accounts, picks and the leaderboard."""

from datetime import datetime, timezone

import auth
import db
import game


def signup(client, nick="Bulldog", pw="correct horse battery", avatar="lincoln"):
    return client.post("/api/signup", json={"nickname": nick, "password": pw, "avatar": avatar})


def test_password_is_hashed_never_stored(client):
    assert signup(client).status_code == 200
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users").fetchone()
    assert row["password_hash"].startswith("pbkdf2_sha256$600000$")
    assert "correct horse battery" not in row["password_hash"]
    assert "email" not in row.keys()


def test_session_token_is_hashed(client):
    r = signup(client)
    token = r.cookies.get("mt_session")
    with db.connect() as conn:
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert token and token != stored and len(stored) == 64


def test_api_never_returns_password_hash(client):
    body = signup(client).text + client.get("/api/me").text + client.get("/api/leaderboard").text
    assert "pbkdf2" not in body and "password" not in body


def test_duplicate_nickname_rejected(client):
    signup(client)
    client.post("/api/logout")
    assert signup(client, nick="BULLDOG").status_code == 409


def test_bad_inputs_rejected(client):
    assert signup(client, pw="short").status_code == 400
    assert signup(client, avatar="not-an-avatar").status_code == 400
    assert signup(client, nick="<script>").status_code == 400


def test_login_lockout_after_repeated_failures(client):
    signup(client); client.post("/api/logout")
    codes = [client.post("/api/login", json={"nickname": "bulldog", "password": f"wrong-{i}"}).status_code for i in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # even the right password is refused while locked out
    assert client.post("/api/login", json={"nickname": "bulldog", "password": "correct horse battery"}).status_code == 429
    auth._failures.clear()


def test_picks_validated_and_saved(client):
    signup(client)
    assert client.put("/api/picks", json={"picks": {"sen-tx": "R", "sen-ne": "I"}}).status_code == 200
    assert client.put("/api/picks", json={"picks": {"sen-tx": "Z"}}).status_code == 400       # not a candidate
    assert client.put("/api/picks", json={"picks": {"ny-08": "D"}}).status_code == 400        # not a prediction race
    assert client.get("/api/me").json()["picks"] == {"sen-tx": "R", "sen-ne": "I"}


def test_picks_need_login(client):
    assert client.put("/api/picks", json={"picks": {"sen-tx": "R"}}).status_code == 401


def test_picks_lock_on_election_day():
    user = auth.create_user("Late Voter", "correct horse battery", "fdr")
    after = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    try:
        game.save_picks(user["id"], {"sen-tx": "R"}, at=after)
        assert False, "picks should be closed"
    except game.GameError as e:
        assert e.status == 403


def test_leaderboard_names_only_until_results_then_points(client):
    signup(client); client.put("/api/picks", json={"picks": {"sen-tx": "R", "sen-oh": "D"}}); client.post("/api/logout")
    signup(client, nick="Ann", avatar="fdr"); client.put("/api/picks", json={"picks": {"sen-tx": "D", "sen-oh": "D"}})
    lb = client.get("/api/leaderboard").json()
    assert lb["live"] is False and all(p["points"] is None for p in lb["players"])
    assert "picks" not in str(lb["players"])                     # nobody's picks are published
    game.approve_result("sen-tx", "R", "test"); game.approve_result("sen-oh", "D", "test")
    lb = client.get("/api/leaderboard").json()
    assert lb["live"] and [(p["nickname"], p["points"]) for p in lb["players"]] == [("Bulldog", 20), ("Ann", 10)]


def test_crowd_is_counts_only(client):
    signup(client); client.put("/api/picks", json={"picks": {"sen-tx": "R"}})
    assert client.get("/api/crowd").json() == {"crowd": {"sen-tx": {"R": 1}}}


def test_cross_site_write_blocked(client):
    signup(client)
    r = client.put("/api/picks", json={"picks": {"sen-tx": "R"}}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
