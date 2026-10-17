# 2026 Midterm Tracker

MGT 409 final project. The site shows every 2026 Senate and governor race, plus the 30 closest House races. For each race you can compare ratings from 10 forecasters, see a model prediction, and make your own pick.

**Live site:** https://mccrocken27.github.io/midterm-tracker/

## What's on the site

- **US map** with Senate, Governor, and House layers. Each state is colored by the forecasters' consensus.
- **Click any state** to see its races, each outlet's rating with its date, an experimental model prediction, and buttons for your own pick.
- **Avatars** are party mascots, not likenesses: donkeys for Democrats and elephants for Republicans. A Y patch marks a candidate the Yale Alumni Magazine lists as a Yale alumnus.

## Run it locally

The site is one self-contained HTML file with no build step and no API key.

1. Clone the repo.
2. Open `docs/index.html` in a browser.

## Data

Ratings were collected by hand from public pages (Cook, Inside Elections, Sabato, The Economist, Split Ticket, Decision Desk HQ, FiftyPlusOne, Fox News, Silver Bulletin, RealClearPolitics, and Race to the WH for governor races). They are dated Aug 11 to Oct 16, 2026. A blank rating means it wasn't collected, not that the outlet has no opinion. The model prediction is experimental and has not been checked against past elections.
