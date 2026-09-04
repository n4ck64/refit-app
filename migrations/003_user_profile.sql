
CREATE TABLE IF NOT EXISTS user_profile (
  user_id    integer PRIMARY KEY REFERENCES "user" (user_id),
  profile    jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamp NOT NULL DEFAULT now()
);

COMMENT ON COLUMN user_profile.profile IS
  'Slots: conditions, medications, injuries, goals, equipment, constraints, other. '
  'Merged from conversation each turn; never overwritten wholesale. '
  'Contains health data — belongs inside the field-level encryption scope.';
