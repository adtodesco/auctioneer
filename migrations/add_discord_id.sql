-- Migration: Add discord_id column to user table
-- Date: 2026-02-13

-- Add discord_id column (nullable)
ALTER TABLE user ADD COLUMN discord_id VARCHAR;

-- Make slack_id nullable (if it wasn't already)
-- Note: SQLite doesn't support modifying column constraints directly,
-- so this is only needed if slack_id was previously NOT NULL.
-- Since we're already running this, the Python model change will handle it.
