-- Seeds the six synthetic test users behind the dev user-switcher, and the
-- profile for user 1 used by the persona-tailoring demo.
-- Run AFTER exercise_schema.sql and migrations/003_user_profile.sql.
--   psql -d exercise_database -f data/seed_users.sql

INSERT INTO "user" (user_id, username, full_name, email, gender, date_of_birth) VALUES
  (1, 'swinchester', 'Sam Winchester', 'sam.winchester@example.com', 'M', '1984-03-15'),
  (2, 'lokafor',     'Leo Okafor',     'leo.okafor@example.com',     'M', '2004-06-02'),
  (3, 'rmcreary',    'Rita McReary',   'rita.mcreary@example.com',   'F', '2000-11-20'),
  (4, 'dmarsh',      'David Marsh',    'david.marsh@example.com',    'M', '1974-01-30'),
  (5, 'madeyemi',    'Marcus Adeyemi', 'marcus.adeyemi@example.com', 'M', '1990-03-11'),
  (6, 'lsuping',     'Li Suping',      'li.suping@example.com',      'F', '1952-05-18')
ON CONFLICT (user_id) DO NOTHING;

-- Users 2-6 build their profiles through conversation; user 1 is pre-populated
-- so the tailoring behaviour is demonstrable without a full intake first.
INSERT INTO user_profile (user_id, profile) VALUES
  (1, '{"goals": ["lose weight"], "other": [], "injuries": ["right shoulder pain", "worse overhead"], "equipment": [], "conditions": ["high blood pressure"], "constraints": [], "medications": ["bisoprolol"]}'::jsonb)
ON CONFLICT (user_id) DO NOTHING;
