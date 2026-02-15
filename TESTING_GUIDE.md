# End-to-End Auction Notification System Testing Guide

## Phase 1: Code Changes ✅ COMPLETED

The notification timing has been converted from hours to minutes throughout the codebase. This allows rapid testing of the entire auction cycle.

**Files Modified:**
- `auctioneer/config.py` - Updated `get_notification_alert_minutes()`
- `auctioneer/commands.py` - Changed config key to `NOTIFICATION_ALERT_MINUTES`
- `auctioneer/discord.py` - Updated notification functions and message text
- `auctioneer/slack.py` - Updated notification functions and message text

**Changes Committed:** ✅ Ready to deploy

---

## Phase 2: Discord Setup

### Prerequisites

1. **Discord Server**: Create a test Discord server (or use existing)

2. **Webhook URL**:
   - Server Settings → Integrations → Webhooks → New Webhook
   - Name it "Auctioneer Test Bot" or similar
   - Select a channel (e.g., #auction-alerts)
   - Copy webhook URL

3. **Discord IDs** (for testing @mentions):
   - Enable Developer Mode: User Settings → Advanced → Developer Mode
   - Right-click on users → Copy ID
   - Save these IDs for adding to user profiles

### Configuration Steps

**Option A: Via Environment Variable (before deployment)**
```bash
# Add to web.env file:
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL
NOTIFICATION_TYPE=discord
```

**Option B: Via Admin UI (after deployment)**
1. Navigate to `/admin/config/`
2. Edit `DISCORD_WEBHOOK_URL` - paste your webhook URL
3. Edit `NOTIFICATION_TYPE` - set to `discord`
4. For each test user:
   - Navigate to `/users/<user_id>/edit/`
   - Add their Discord ID in the discord_id field

### Test Users to Create

- **User A**: Add Discord ID (will test @mention functionality)
- **User B**: Leave Discord ID empty (will test fallback to team name)

---

## Phase 3: Database Migration

After deploying the code changes, update the database config table:

### Option 1: SQL Update (Preserves Existing Data)

```bash
# SSH into the server and run:
docker exec -it auctioneer-web-1 flask shell

# In the Flask shell:
from auctioneer import db
db.session.execute(db.text("""
    UPDATE config
    SET key = 'NOTIFICATION_ALERT_MINUTES',
        description = 'Minutes before an event to send alert notifications'
    WHERE key = 'NOTIFICATION_ALERT_HOURS'
"""))
db.session.commit()
exit()
```

### Option 2: Reinitialize Database (Only if Acceptable to Lose Data)

```bash
docker exec -it auctioneer-web-1 flask init-db
```

**Note:** After migration, verify the config:
```bash
docker exec -it auctioneer-web-1 flask shell
from auctioneer.config import get_notification_alert_minutes
print(get_notification_alert_minutes())  # Should print: 2
exit()
```

---

## Phase 4: Test Data Setup

### Create Test Slot

Navigate to `/slots/` admin interface and create:

```
Round Number: 99
Opens At: [Current time + 1 minute]
Closes At: [Current time + 5 minutes]
```

This creates a 5-minute auction window for testing.

**Expected Notifications Created Automatically:**
1. "Round 99 nomination period has begun" - sent at `opens_at`
2. "Round 99 nomination period ends in 2 minutes!" - sent 2 minutes before `closes_at`
3. "Round 99 auctions close in 2 minutes!" - sent 2 minutes before `closes_at`

### Create Test Players

Navigate to `/admin/players/` and create:

**Player 1:**
- Name: Test Player A
- Team: Any team
- Position: Any position
- Matcher: Leave empty (no match rights)

**Player 2:**
- Name: Test Player B
- Team: Any team
- Position: Any position
- Matcher: Select User A (for testing match functionality)

---

## Phase 5: End-to-End Test Execution

### Setup (Minute 0)

```bash
# SSH into server
ssh user@your-server

# Watch cron logs in real-time
docker exec -it auctioneer-web-1 tail -f /var/log/cron.log

# In another terminal, watch application logs
docker-compose logs -f web
```

### Timeline

**Minute 1 - Nomination Period Opens:**
- ✅ Check Discord: "Round 99 nomination period has begun"
- Create nominations via UI:
  - User A nominates Test Player A
  - User B nominates Test Player B
- ✅ Check Discord: Should receive nominations notifications with proper @mentions

**Minute 2-3 - Place Bids:**
- User A: Bid $100 on Test Player A
- User B: Bid $150 on Test Player B

**Minute 3 - Alert Notifications:**
- ✅ Check Discord: Should receive TWO notifications:
  - "Round 99 nomination period ends in 2 minutes!"
  - "Round 99 auctions close in 2 minutes!"

**Minute 5 - Auctions Close:**
- Watch cron log: Should show "Closed 2 nominations"
- ✅ Check Discord: Should receive:
  - "User B won Test Player A for $100!" (with @mention or team name)
  - "User A has 24 hours to match..." for Test Player B (with @mention)

**Minute 6+ - Match Decision:**
- User A navigates to `/match/<nomination_id>/`
- Verify:
  - ✅ Match page shows correct winning bid ($150)
  - ✅ If hometown discount applies: shows 90% price
  - ✅ Decision buttons work correctly
- Select "Yes" to match
- ✅ Check Discord: Match notification removed/updated

**Minute 7+ - Sign Players:**
- User B signs Test Player A via `/sign/<player_id>/`
- User A signs Test Player B via `/sign/<player_id>/`
- Verify:
  - ✅ Contract options correct based on bid values
  - ✅ Signing completes successfully

---

## Phase 6: Verification Checklist

### Cron Jobs
- [ ] `close-nominations` runs every minute (check `/var/log/cron.log`)
- [ ] `send-notifications` runs every minute (check `/var/log/cron.log`)
- [ ] Nominations close exactly at slot `closes_at` time
- [ ] Match nominations close 24 hours after slot `closes_at`

### Discord Notifications
- [ ] Webhook URL works (messages appear in Discord channel)
- [ ] Message formatting is clean (bold text, embeds, emojis)
- [ ] Nomination period begun notification sent at correct time
- [ ] Alert notifications sent 2 minutes before events
- [ ] Player nominated notifications include nominator mention/team name
- [ ] Auction won notifications include winner mention/team name
- [ ] Match pending notifications include matcher mention/team name

### Discord ID Tagging
- [ ] User with Discord ID: Notification contains `<@DISCORD_ID>` and user is @mentioned
- [ ] User without Discord ID: Notification contains plain team name
- [ ] Fallback logic works for all notification types

### Edge Cases
- [ ] Multiple simultaneous auctions in same round work correctly
- [ ] Notifications not duplicated if cron runs multiple times
- [ ] Hometown discount calculation correct in match notifications
- [ ] Database `sent` flag prevents duplicate notifications

### UI Integration
- [ ] Notification timestamps display correctly in ET timezone
- [ ] Match page shows correct times and bid amounts
- [ ] Auction cards show correct status (OPEN → MATCHING → CLOSED)

---

## Phase 7: Test Data Cleanup

After testing is complete, clean up test data:

### Via UI
1. Navigate to `/slots/` - Delete Round 99 slot
2. Navigate to `/admin/players/` - Delete test players

### Via Database (if needed)
```bash
docker exec -it auctioneer-web-1 flask shell

from auctioneer import db
from auctioneer.model import Notification, Nomination, Slot, Player

# Delete test notifications
db.session.execute(db.text("DELETE FROM notification WHERE title LIKE '%Round 99%'"))

# Delete test nominations (if any remain)
db.session.execute(db.text("DELETE FROM nomination WHERE slot_id IN (SELECT id FROM slot WHERE round = 99)"))

# Delete test slot
db.session.execute(db.text("DELETE FROM slot WHERE round = 99"))

# Delete test players
db.session.execute(db.text("DELETE FROM player WHERE name LIKE 'Test Player%'"))

db.session.commit()
exit()
```

---

## Critical Files Reference

### Files Modified (Already Deployed)
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer/config.py` (line 148-150)
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer/commands.py` (line 108-113)
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer/discord.py` (lines 10, 47-75, 85-107)
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer/slack.py` (lines 8, 45-73, 83-105)

### Files to Monitor During Testing
- Cron log: `docker exec auctioneer-web-1 tail -f /var/log/cron.log`
- Application logs: `docker-compose logs -f web`

### Files Referenced
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer-cron` - Cron schedule
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer/commands.py` (lines 145-214) - Commands
- `/Users/anthonytodesco/Projects/auctioneer/auctioneer/model.py` (lines 14, 112-120) - Models

---

## Troubleshooting

### Notifications Not Sending
1. Check webhook URL is set: `docker exec -it auctioneer-web-1 flask shell`
   ```python
   from auctioneer.config import get_config
   print(get_config("DISCORD_WEBHOOK_URL"))
   ```
2. Check cron is running: `docker exec -it auctioneer-web-1 ps aux | grep cron`
3. Check logs: `docker-compose logs -f web`

### @Mentions Not Working
1. Verify Discord ID format (should be numeric, e.g., `123456789012345678`)
2. Verify Developer Mode is enabled in Discord
3. Check user record: Navigate to `/users/<id>/edit/` and verify discord_id field

### Cron Jobs Not Running
1. Check cron service: `docker exec -it auctioneer-web-1 service cron status`
2. Check cron file: `docker exec -it auctioneer-web-1 cat /etc/cron.d/auctioneer-cron`
3. Restart cron: `docker exec -it auctioneer-web-1 service cron restart`

### Auctions Not Closing
1. Check slot times are in UTC
2. Verify current time: `docker exec -it auctioneer-web-1 date -u`
3. Check nomination status in database

---

## Next Steps After Testing

1. **Keep the code changes** - Minutes-based timing is now permanent
2. **Update production config** - Set `NOTIFICATION_ALERT_MINUTES` to desired value (e.g., 120 for 2 hours)
3. **Document for future** - Add notes about minute-based timing to admin documentation
4. **Monitor production** - Watch first few rounds closely to ensure notifications work as expected

---

## Success Criteria

Testing is successful when:
- ✅ All notifications are received in Discord at correct times
- ✅ @Mentions work for users with Discord IDs
- ✅ Fallback to team names works for users without Discord IDs
- ✅ Auctions close automatically at the correct time
- ✅ Match functionality works correctly
- ✅ No duplicate notifications are sent
- ✅ All UI pages display correct information

**Keep this file for reference during testing!**
