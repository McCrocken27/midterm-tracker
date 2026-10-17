# 2026 Midterm Tracker

MGT 409 final project. The site shows every 2026 Senate and governor race, plus 162 House races (every seat at least one forecaster rates competitive, big names like Hakeem Jeffries and Mike Johnson, and at least one seat in every state), and a searchable list of all 435 House seats. For each race you can compare ratings from 10 forecasters, see a model prediction, and make your own pick.

**Live site:** https://mccrocken27.github.io/midterm-tracker/

## What's on the site

- **US map** with Senate, Governor, and House layers. Each state is colored by the forecasters' consensus.
- **Click any state** to see its races, each outlet's rating with its date, an experimental model prediction, and buttons for your own pick.
- **Avatars** are party mascots, not likenesses: donkeys for Democrats, elephants for Republicans, and eagles for independents with a real shot (Dan Osborn in Nebraska, Seth Bodnar in Montana). A Y patch marks a verified Yale alumnus, and a shamrock marks a verified Notre Dame alumnus. About 35 well-known candidates (the top Senate races, big-name governor candidates, and House leaders like Mike Johnson and Hakeem Jeffries) get friendly signature props: hair, glasses, hats, or a pin like Sherrod Brown's canary. They never change skin, body, or face.
- **Joey**, a made-up "former campaign expert", has his own calls on 37 key races, and he picks the favorite in every seat rated Safe.
- **Every House seat** tab: all 435 districts with incumbent, candidates, lean, and rating, searchable by district, state, or name.
- **Predict and compare** tab: players pick a nickname and a cartoon Labubu avatar (Joey, the Statue of Liberty, or one dressed like a president or vice president: Washington, Lincoln, Teddy Roosevelt, FDR, Truman, Eisenhower, JFK, Reagan, Obama, Trump, Biden, Vance, Harris). They are suggested by hats, hair and clothes, not faces, then pick winners in 37 key races and compare them with the crowd, the forecasters, the model, and Joey. A leaderboard turns on once results are entered. On GitHub Pages, picks are saved in each visitor's own browser.
- **Vote** tab: enter an address to see your Senate, governor, and House races, the candidates and their parties, and a link to your state's official voter registration page. The address goes once to the U.S. Census Bureau's free geocoder (which returns the new 2026 districts), is cleared from the page immediately, and is never stored. Lookups are capped at 10 per visit.
- Only major candidates are shown: a major-party nominee, or anyone with better than a 20% chance of winning.

## Run it locally

The site is one self-contained HTML file with no build step and no API key.

1. Clone the repo.
2. Open `docs/index.html` in a browser.

## Data

Ratings were collected by hand from public pages (Cook, Inside Elections, Sabato, The Economist, Split Ticket, Decision Desk HQ, FiftyPlusOne, Fox News, Silver Bulletin, RealClearPolitics, and Race to the WH for governor races). They are dated Aug 11 to Oct 16, 2026. House ratings and nominees come from Wikipedia's 2026 House election pages (ratings dated Oct 7 to 16, Silver Bulletin Sep 10). The House model prediction is a fit to the earlier model: Dem % = 67.8 + 15.7 × rating score + 2.1 × district lean. A blank rating means it wasn't collected, not that the outlet has no opinion. The model prediction is experimental and has not been checked against past elections.
