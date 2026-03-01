# Auctioneer - "The Doo Auction"

Sealed-bid auction system for a dynasty baseball fantasy league (hosted on Fantrax). Deployed at thedooauction.com.

## Tech Stack

- **Backend**: Flask 2.2.2, SQLAlchemy 1.4.46, SQLite
- **Frontend**: Jinja2 templates, vanilla JS/CSS
- **Deployment**: Docker + Docker Compose, Nginx (SSL), Gunicorn
- **Notifications**: Discord webhooks (also supports Slack)
- **Cron**: Runs every minute in container for `close-nominations` and `send-notifications`

## Project Structure

```
auctioneer/
├── __init__.py          # App factory, blueprint registration, CLI commands
├── model.py             # SQLAlchemy models (User, Player, Slot, Nomination, Bid, etc.)
├── config.py            # Config management (stored in DB Config table)
├── auction.py           # Core auction logic (nominate, bid, match, sign, results)
├── commands.py          # CLI commands (close-nominations, send-notifications)
├── notifications.py     # Notification routing (Discord/Slack)
├── discord.py           # Discord webhook implementation
├── slack.py             # Slack webhook implementation
├── players.py           # Player management & Fantrax CSV import
├── slots.py             # Auction round/slot management
├── users.py             # Team/user management
├── rosters.py           # Roster view & salary cap tracking
├── tiebreaker.py        # Tiebreaker order management
├── auth.py              # Login/registration
├── audit_log.py         # Audit trail
├── utils.py             # Helpers
├── constants.py         # MLB teams & positions
├── data/
│   ├── users.csv        # Team config (imported at init)
│   └── players.csv      # Fantrax player export (imported at init)
├── templates/           # Jinja2 templates
└── static/              # CSS, JS, images
```

## How the Auction Works

1. **Nomination**: Each user nominates a player during a round's nomination window and places an initial bid (min $11)
2. **Sealed Bidding**: All users place hidden bids on nominated players
3. **Auction Close**: Highest bid wins. Ties broken by tiebreaker order (winner drops to bottom)
4. **Match Rights**: If a player has a matcher (assigned by commissioner), the matcher gets 24h to match the winning bid
5. **Hometown Discount (HTD)**: If enabled, matcher pays 90% of winning bid (ceil, min $11)
6. **Signing**: Winner selects contract length (1-10 years). Salary = ceil(bid / (contract_year - base_year))

## Key Data Models

- **User**: Team in the league (username, team_name, tiebreaker_order, discord_id)
- **Player**: Has fantrax_id, name, team, position, salary, contract (year 2026-2035), manager_id (owner), matcher_id (match rights), hometown_discount flag
- **Slot**: Auction round with timing (closes_at, nomination_opens_at, nomination_closes_at)
- **Nomination**: Links a player to a slot, tracks nominator
- **Bid**: Sealed bid (user_id, nomination_id, value)
- **Config**: Key-value store for all league settings (salary caps, min bids, match time, etc.)

## Configuration (stored in Config table)

- `SALARY_CAP`: JSON dict of per-year caps (2026-2035)
- `MINIMUM_TOTAL_SALARY`: JSON dict of min salary by contract length (1-10 years)
- `MINIMUM_BID_VALUE`: Default $11
- `MATCH_TIME_HOURS`: Default 24
- `NOTIFICATION_TYPE`: 'discord' or 'slack'
- `DISCORD_WEBHOOK_URL` / `SLACK_WEBHOOK_URL`: Webhook URLs

## CSV Results Export

Route `GET /results/` exports `the-doo-auction-results.csv` with columns:
`Fantrax ID, Round, Player, Team, Position, Winner, Salary, Contract, Bids`

Only includes signed players. Bids are semicolon-separated.

## Fantrax Player Import

Route `/admin/players/import/` accepts a CSV exported from Fantrax with columns:
`ID, Player, Team, Position, Status, Salary, Contract`

Optional columns: `Match Rights`, `Hometown Discount`

Status "FA" = free agent. Otherwise Status is a team short name mapping to a user.

## Running Locally

```bash
# Flask dev server
flask --app auctioneer run --debug

# Or with Docker
docker-compose up --build
```

## Environment

- `web.env`: Contains SECRET_KEY, webhook URLs, NOTIFICATION_TYPE
- Database: `instance/auctioneer.sqlite` (auto-created by `flask init-db`)
