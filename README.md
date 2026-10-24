# 2026 Midterm Tracker

MGT 409 final project. A kid-friendly election site covering every 2026 Senate and governor race and all 435 House races. Compare 10 forecasters side by side, see a model prediction, make your own picks on a shared leaderboard, find the races on your own ballot, and ask **Joey**, an AI agent team, about any race.

**Public demo (map, ratings, picks in your own browser):** https://mccrocken27.github.io/midterm-tracker/
**Full app (accounts, shared leaderboard, Ask Joey agents):** run it locally with the steps below.

## Run it locally (about 5 minutes)

You need Python 3.11 or newer and the course `PORTKEY_API_KEY`.

1. **Get the code.**
   ```
   git clone https://github.com/McCrocken27/midterm-tracker.git
   cd midterm-tracker
   ```
2. **Add your key.** Copy `.env.example` to `.env` and paste your `PORTKEY_API_KEY` after the `=`.
   The app looks for `.env` in this folder first, then in the folder above it, so a `.env` one folder up works too.
3. **Install** (from the `backend` folder):
   - Windows:
     ```
     cd backend
     python -m venv .venv
     .\.venv\Scripts\python -m pip install -r requirements.txt
     ```
   - Mac / Linux:
     ```
     cd backend
     python3 -m venv .venv
     .venv/bin/python -m pip install -r requirements.txt
     ```
4. **Start the server** (still in `backend`):
   - Windows: `.\.venv\Scripts\python -m uvicorn main:app --port 8000` (the leading `.\` is needed in PowerShell; it also works in Command Prompt)
   - Mac / Linux: `.venv/bin/python -m uvicorn main:app --port 8000`
5. **Open http://127.0.0.1:8000.** To check the setup, open http://127.0.0.1:8000/api/health. It should say `"key_found": true`.

Then go to **Predict and Compare**, pick an avatar, and sign up with any nickname and password (no email). Make picks, press **Save my picks**, and you're on the shared leaderboard. Once you're logged in, open the **Ask Joey** tab and ask about any race.

**Run the tests** (no key needed, and no model calls): `.\.venv\Scripts\python -m pytest` (Mac: `.venv/bin/python -m pytest`)

## What's on the site

- **Map** with Senate, Governor, and House layers, colored by the forecasters' consensus. Click a state to see its races; the race details open right under the race you click.
- **Balance of Power and What If?:** a bar above the map shows how the Senate (counting seats not on the ballot), House, or governor races split if every race goes the way the forecasters lean. Turn on What If? mode to pick your own winners (or fill in Joey's calls) and watch the bars and map change. Picks stay in your browser.
- **Election Night mode:** results come in state by state, east to west. The map fills in, a ticker lists winners, the bars count called seats, and confetti pops when one of your picks is right. Before results exist it runs a clearly labeled practice (your What If picks, else the forecasters' favorite, and Joey's call in toss-ups).
- **News:** headlines about 2026 races from free feeds (Google News, NPR, PBS), with a search box and Senate/Governor/House filters. Each story is tagged with the race it's about, and race details show "In the news." `backend/news.py` collects them into `docs/news.json`, skipping off-topic, paywalled, social-media, and not-kid-friendly stories. A GitHub Action (`.github/workflows/news.yml`) reruns it every 4 hours; run `python backend/news.py` to refresh by hand.
- **Private leagues** (needs the server): make a league and share its 8-character join code so friends get their own leaderboard. Codes have no vowels (they can't spell words), join attempts are rate limited, league names must be kid-friendly, and only members can see a league. See `backend/leagues.py`.
- **Civics Quiz with Joey:** 10 random questions (from 20) about how elections work, with Joey cheering you on. No AI and no account; your best score stays in your browser and doesn't count on the leaderboard.
- **Badges:** Full Ballot, Bold Pick, Toss-up Tamer, and (after results) Upset Caller, Sharpshooter, and Beat Joey. They show next to your name on the leaderboard and never say which races you picked. The server computes them (`backend/game.py`) with the same rules as the site.
- **Predict and Compare:** nickname and password accounts with a Labubu avatar. Pick winners in 50 key races. The shared leaderboard shows only avatars and names until Election Day, then 10 points per correct call.
- **What are the Midterms?:** a plain-language explainer for newcomers: what the midterms are, what's on the ballot (435 House, 35 Senate, 36 Governor races), why control of Congress and governors matters, who can vote, how to read the site, and a short glossary, with buttons to the other tabs.
- **Races to Watch:** a starting point for newcomers. The 50 Predict and Compare races plus every race the forecasters rate a Toss-up or Tilt (45 right now), grouped by Senate, governor and House, closest first, each with the rating, Joey's call and a button to open it on the map. At the bottom, "See every House seat" opens the full searchable list of all 435 districts (names link to Ballotpedia, which lists each campaign's website).
- **Vote:** enter an address to see your races and your state's official registration page. The address is sent once to the U.S. Census geocoder, cleared immediately, and never stored. Capped at 10 lookups per visit.
- **Ask Joey:** questions answered by an agent team (below).
- Mascots, not likenesses: donkeys for Democrats, elephants for Republicans, eagles for independents. Some well-known candidates get friendly props (hair, glasses, hats, pins). A Y marks verified Yale alumni and a shamrock verified Notre Dame alumni.

## The agents

```
question -> safety screen (code) -> Router -> Researcher (read-only tools) -> Analyst "Joey" -> Verifier (code) -> output filter (code)
```

| Agent | Job | Tools |
|---|---|---|
| Router | Works out which races a question is about, or that it's off topic | none (structured output) |
| Researcher | Looks up the facts | `get_race`, `list_races` (read-only race data) |
| Analyst "Joey" | Writes a short, friendly answer using only those facts | none |
| Verifier (code) | Every number in the answer must appear in the facts; one retry, then a data-only answer | n/a |
| Results agent | Reads results pages on election night and suggests winners | none; a person approves each suggestion |

Model: `gpt-6-luna` through Portkey, using PydanticAI.

## Safety

- **No emails or real names** are collected. Passwords are stored only as salted PBKDF2 hashes (600,000 rounds), and session cookies are HttpOnly with only their SHA-256 hash stored.
- **Login lockout** after 5 wrong passwords per nickname (20 per IP). Rate limits on sign-ups and questions.
- **The agents can't reach private data:** no agent tool touches accounts, passwords, sessions, or picks.
- **Prompt-injection screen** before any agent runs, an **output filter** that blocks anything that looks like a hash, key, token, or email, and the **Verifier** that blocks made-up numbers.
- **Results need a human:** `results_agent.py` only suggests winners from a results page (stripped and fenced as data, with planted instructions flagged), and `approve.py` asks a person to approve each one.
- **Cost caps:** at most 10 model requests and 10 tool calls per agent run, 800 output tokens per response, a daily token budget (200,000 by default), and a 30-minute answer cache.
- **Cross-site writes are blocked**, and every query uses SQL placeholders.
- `tests/test_safety.py` runs each attack and checks that it's stopped.

## Election night

```
cd backend
.\.venv\Scripts\python results_agent.py <results page URL>    # the agent suggests winners
.\.venv\Scripts\python approve.py                              # you approve or reject each one
.\.venv\Scripts\python approve.py set sen-tx R                 # or enter a result by hand
.\.venv\Scripts\python usage_report.py                         # tokens per question, safety log
```

## Data

Statewide ratings were collected from public pages (Cook, Inside Elections, Sabato, The Economist, Split Ticket, Decision Desk HQ, FiftyPlusOne, Fox News, Silver Bulletin, RealClearPolitics, and Race to the WH for governors), dated Aug 11 to Oct 22, 2026. House ratings and nominees come from Wikipedia's 2026 House election pages. Seats not on Wikipedia's competitive list are rated Safe by every outlet. The model prediction is experimental: for the House, Dem % = 67.8 + 15.7 × rating score + 2.1 × district lean. Joey is a made-up character, not a real analyst.
