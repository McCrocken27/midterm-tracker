"""Private leagues: codes, membership, privacy and limits."""

import game
import leagues
import safety


def signup(client, nick, avatar="lincoln"):
    r = client.post("/api/signup", json={"nickname": nick, "password": "correct horse battery", "avatar": avatar})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def test_make_join_and_league_leaderboard(client):
    signup(client, "Bulldog")
    lg = client.post("/api/leagues", json={"name": "Yale Friends"}).json()["league"]
    assert len(lg["code"]) == leagues.CODE_LEN and not set(lg["code"]) & set("AEIOU")   # no vowels: never spells a word
    client.put("/api/picks", json={"picks": {"sen-tx": "R"}}); client.post("/api/logout")

    signup(client, "Ann", "fdr")
    assert client.post("/api/leagues/join", json={"code": lg["code"].lower()}).json()["league"]["members"] == 2  # any case works
    client.post("/api/logout")
    signup(client, "Outsider", "jfk"); client.put("/api/picks", json={"picks": {"sen-tx": "D"}})

    # members see only members; Ann has no picks yet but still shows up in her league
    client.post("/api/logout"); client.post("/api/login", json={"nickname": "Ann", "password": "correct horse battery"})
    board = client.get(f"/api/leagues/{lg['id']}/leaderboard").json()
    assert sorted(p["nickname"] for p in board["players"]) == ["Ann", "Bulldog"]
    game.approve_result("sen-tx", "R", "test")
    board = client.get(f"/api/leagues/{lg['id']}/leaderboard").json()
    assert [(p["nickname"], p["points"]) for p in board["players"]] == [("Bulldog", 10), ("Ann", 0)]


def test_outsiders_cant_see_a_league(client):
    signup(client, "Bulldog")
    lg = client.post("/api/leagues", json={"name": "Secret Club"}).json()["league"]
    client.post("/api/logout"); signup(client, "Snoop", "jfk")
    assert client.get(f"/api/leagues/{lg['id']}/leaderboard").status_code == 404
    assert client.get("/api/leagues").json() == {"leagues": []}
    client.post("/api/logout")
    assert client.get("/api/leagues").status_code == 401                    # and you need an account at all


def test_bad_codes_and_guessing_are_limited(client):
    signup(client, "Guesser")
    assert client.post("/api/leagues/join", json={"code": "BCDFGHJK"}).status_code == 404
    codes = [client.post("/api/leagues/join", json={"code": "BCDFGHJK"}).status_code for _ in range(12)]
    assert 429 in codes                                                      # rate limited after 10 tries an hour


def test_league_names_must_be_kid_friendly(client):
    signup(client, "Bulldog")
    for bad in ["sh1t heads", "Stupid Losers", "<script>", "ab"]:
        assert client.post("/api/leagues", json={"name": bad}).status_code == 400, bad
    for ok in ["Grapefruit League", "Hancock Hall", "Hello Friends!"]:
        assert safety.kid_friendly(ok), ok


def test_owner_leaving_deletes_the_league(client):
    signup(client, "Bulldog")
    lg = client.post("/api/leagues", json={"name": "Short Lived"}).json()["league"]
    assert client.post(f"/api/leagues/{lg['id']}/leave").json() == {"ok": True}
    assert client.get("/api/leagues").json() == {"leagues": []}


def test_limit_on_leagues_made(client):
    signup(client, "Bulldog")
    for i in range(leagues.MAX_OWNED):
        assert client.post("/api/leagues", json={"name": f"League {i}"}).status_code == 200
    assert client.post("/api/leagues", json={"name": "One Too Many"}).status_code == 400
