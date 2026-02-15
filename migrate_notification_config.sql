-- Migration script to rename NOTIFICATION_ALERT_HOURS to NOTIFICATION_ALERT_MINUTES
-- Run this after deploying the code changes

-- Update the config table to use minutes instead of hours
UPDATE config
SET key = 'NOTIFICATION_ALERT_MINUTES',
    description = 'Minutes before an event to send alert notifications'
WHERE key = 'NOTIFICATION_ALERT_HOURS';

-- Verify the change
SELECT key, value, description, value_type
FROM config
WHERE key = 'NOTIFICATION_ALERT_MINUTES';
