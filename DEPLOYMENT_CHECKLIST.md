# Deployment Checklist: Notification System Testing

## Pre-Deployment

- [x] **Code Changes Committed**
  - Changed `NOTIFICATION_ALERT_HOURS` → `NOTIFICATION_ALERT_MINUTES` in all files
  - Updated function names from `get_notification_alert_hours()` → `get_notification_alert_minutes()`
  - Changed `timedelta(hours=X)` → `timedelta(minutes=X)` in notification scheduling
  - Updated notification message text to say "X minutes" instead of "X hours"
  - Applied changes to both discord.py and slack.py

- [ ] **Build and Push Docker Images**
  ```bash
  docker-compose build
  docker-compose push
  ```

## Deployment Steps

### 1. Deploy Updated Code

```bash
# SSH to server
ssh user@your-server

# Pull latest images
cd /path/to/auctioneer
docker-compose pull

# Restart services
docker-compose down
docker-compose up -d

# Verify services are running
docker-compose ps
```

### 2. Migrate Database Config

**Option A: Via Flask Shell (Recommended)**
```bash
docker exec -it auctioneer-web-1 flask shell
```
Then run:
```python
from auctioneer import db
db.session.execute(db.text("""
    UPDATE config
    SET key = 'NOTIFICATION_ALERT_MINUTES',
        description = 'Minutes before an event to send alert notifications'
    WHERE key = 'NOTIFICATION_ALERT_HOURS'
"""))
db.session.commit()

# Verify
from auctioneer.config import get_notification_alert_minutes
print(get_notification_alert_minutes())  # Should print: 2
exit()
```

**Option B: Via SQL File**
```bash
# Copy SQL file to container
docker cp migrate_notification_config.sql auctioneer-web-1:/tmp/

# Run migration
docker exec -it auctioneer-web-1 flask shell
# Then manually run SQL or use database client
```

### 3. Configure Discord Webhook

**Environment Variables (web.env):**
```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
NOTIFICATION_TYPE=discord
```

**Or via Admin UI:**
1. Navigate to `/admin/config/`
2. Update `DISCORD_WEBHOOK_URL`
3. Update `NOTIFICATION_TYPE` to `discord`

### 4. Add Discord IDs to Test Users

For each test user:
1. Navigate to `/users/<user_id>/edit/`
2. Add Discord ID in the `discord_id` field
3. Save

To get Discord IDs:
- Enable Developer Mode in Discord: User Settings → Advanced → Developer Mode
- Right-click on user → Copy ID

### 5. Verify Cron Jobs

```bash
# Check cron is running
docker exec -it auctioneer-web-1 service cron status

# Check cron configuration
docker exec -it auctioneer-web-1 cat /etc/cron.d/auctioneer-cron

# Expected output:
# * * * * * root cd /app && flask close-nominations >> /var/log/cron.log 2>&1
# * * * * * root cd /app && flask send-notifications >> /var/log/cron.log 2>&1

# Watch cron logs
docker exec -it auctioneer-web-1 tail -f /var/log/cron.log
```

## Testing Phase

### Create Test Data

1. **Create Test Slot** (via `/slots/`):
   - Round: 99
   - Opens At: [Now + 1 minute]
   - Closes At: [Now + 5 minutes]

2. **Create Test Players** (via `/admin/players/`):
   - Player A: No matcher
   - Player B: Matcher = User A

### Execute Test Timeline

Follow the detailed timeline in `TESTING_GUIDE.md`:
- Minute 0: Setup monitoring
- Minute 1: Nomination period opens, create nominations
- Minute 2-3: Place bids
- Minute 3: Receive alert notifications
- Minute 5: Auctions close, receive won/match notifications
- Minute 6+: Test match decision
- Minute 7+: Test player signing

### Verify All Checkboxes

See `TESTING_GUIDE.md` Phase 6 for complete verification checklist.

## Post-Testing

### Clean Up Test Data

```bash
docker exec -it auctioneer-web-1 flask shell
```
```python
from auctioneer import db

# Delete test notifications
db.session.execute(db.text("DELETE FROM notification WHERE title LIKE '%Round 99%'"))

# Delete test nominations
db.session.execute(db.text("DELETE FROM nomination WHERE slot_id IN (SELECT id FROM slot WHERE round = 99)"))

# Delete test slot
db.session.execute(db.text("DELETE FROM slot WHERE round = 99"))

# Delete test players (if created specifically for testing)
db.session.execute(db.text("DELETE FROM player WHERE name LIKE 'Test Player%'"))

db.session.commit()
exit()
```

### Update Production Config

Set notification alert time to production value (e.g., 120 minutes = 2 hours):

```bash
docker exec -it auctioneer-web-1 flask shell
```
```python
from auctioneer import db
from auctioneer.model import Config

config = Config.query.filter_by(key='NOTIFICATION_ALERT_MINUTES').first()
config.value = '120'  # 2 hours in minutes
db.session.commit()
exit()
```

## Rollback Plan

If issues are found during testing:

1. **Revert to Previous Docker Images**
   ```bash
   docker-compose down
   # Edit docker-compose.yml to use previous image tag
   docker-compose up -d
   ```

2. **Revert Database Config**
   ```bash
   docker exec -it auctioneer-web-1 flask shell
   ```
   ```python
   from auctioneer import db
   db.session.execute(db.text("""
       UPDATE config
       SET key = 'NOTIFICATION_ALERT_HOURS',
           description = 'Hours before an event to send alert notifications'
       WHERE key = 'NOTIFICATION_ALERT_MINUTES'
   """))
   db.session.commit()
   exit()
   ```

## Success Criteria

Deployment is successful when:
- [x] Code deployed without errors
- [ ] Database migration completed
- [ ] Discord webhook configured
- [ ] Cron jobs running every minute
- [ ] Test notifications received in Discord
- [ ] @Mentions working for users with Discord IDs
- [ ] Fallback to team names working
- [ ] Auctions closing automatically
- [ ] Match functionality working
- [ ] No duplicate notifications
- [ ] All UI pages displaying correctly

## Support

- **Documentation**: See `TESTING_GUIDE.md` for detailed testing steps
- **SQL Migration**: See `migrate_notification_config.sql`
- **Logs**:
  - Application: `docker-compose logs -f web`
  - Cron: `docker exec -it auctioneer-web-1 tail -f /var/log/cron.log`

## Notes

- The change from hours to minutes is **permanent** - this is not a temporary testing change
- For production use, set `NOTIFICATION_ALERT_MINUTES` to appropriate value (e.g., 120 for 2 hours)
- The minute-based timing enables faster testing cycles without waiting hours/days between actions
- Keep test data minimal and clean up promptly to avoid confusion

---

**Last Updated**: 2026-02-15
**Deployed By**: _________________
**Deployment Date**: _________________
**Testing Completed**: _________________
