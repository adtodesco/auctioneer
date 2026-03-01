-- Migration: Add Fantrax integration fields
-- Date: 2026-03-01

-- Add fantrax_team_id column to user table (nullable)
ALTER TABLE user ADD COLUMN fantrax_team_id VARCHAR;

-- Add fantrax_locked column to player table (non-nullable, default false)
ALTER TABLE player ADD COLUMN fantrax_locked BOOLEAN NOT NULL DEFAULT 0;

-- Populate fantrax_team_id for each team
UPDATE user SET fantrax_team_id = '88wt775umhwsxntj' WHERE short_team_name = 'ALEC';
UPDATE user SET fantrax_team_id = '5by5xkb9mhwsxntj' WHERE short_team_name = 'HENRY';
UPDATE user SET fantrax_team_id = 'el8kszwhmhwsxntj' WHERE short_team_name = 'JENKS';
UPDATE user SET fantrax_team_id = 'bt9aquzrmhwsxntj' WHERE short_team_name = 'JOEY';
UPDATE user SET fantrax_team_id = 'eceu4ikjmhwsxntj' WHERE short_team_name = 'JOHN';
UPDATE user SET fantrax_team_id = 'vsluj35gmhwsxntj' WHERE short_team_name = 'KYLE';
UPDATE user SET fantrax_team_id = '1vk4g336mhwsxntj' WHERE short_team_name = 'LANG';
UPDATE user SET fantrax_team_id = '7ojh7qvimhwsxntj' WHERE short_team_name = 'LFGM';
UPDATE user SET fantrax_team_id = 'xaktrk66mhwsxntj' WHERE short_team_name = 'MDS';
UPDATE user SET fantrax_team_id = 'z2y8nw00mhwsxntj' WHERE short_team_name = 'MURPH';
UPDATE user SET fantrax_team_id = 'dyobr750mhwsxntj' WHERE short_team_name = 'NASER';
UPDATE user SET fantrax_team_id = 'p0gc884rmhwsxntj' WHERE short_team_name = 'ROLLS';
UPDATE user SET fantrax_team_id = '7c3t79l7mhwsxntj' WHERE short_team_name = 'TED';
UPDATE user SET fantrax_team_id = 'f0brxbtvmhwsxntj' WHERE short_team_name = 'TONY';

-- Add FANTRAX_LEAGUE_ID config if it doesn't exist
INSERT OR IGNORE INTO config (key, value, description, value_type)
VALUES ('FANTRAX_LEAGUE_ID', 'z03ha7kumhwsxnte', 'Fantrax league ID for API integration', 'string');
