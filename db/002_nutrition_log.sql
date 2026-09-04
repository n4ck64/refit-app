-- Adds the per-user nutrition tables behind the Nutrition tab: a food diary
-- (food_log) and a place for goal-adjusted targets to override the PHE
-- population guideline (user_nutrition_targets).
--
-- Run with: psql -d exercise_database -f migrations/002_nutrition_log.sql

-- food_log stores food_id + grams rather than the denormalised macros, keeping
-- "foods" the single source of truth — get_food_macros already scales per-100g
-- figures by weight, so the diary reuses that path instead of copying numbers.
-- Trade-off: a CoFID correction would retroactively alter logged history, which
-- is the right behaviour here (the food did not change, the measurement did).
--
-- logged_on is a real column rather than logged_at::date so an entry can be
-- backdated ("I ate this yesterday") without timezone arithmetic.
CREATE TABLE food_log (
  "log_id"    bigserial PRIMARY KEY,
  "user_id"   integer   NOT NULL REFERENCES "user"("user_id"),
  "food_id"   integer   NOT NULL REFERENCES "foods"("id"),
  "grams"     real      NOT NULL CHECK ("grams" > 0),
  "logged_on" date      NOT NULL DEFAULT CURRENT_DATE,
  "logged_at" timestamp NOT NULL DEFAULT now()
);
CREATE INDEX ON food_log ("user_id", "logged_on");

-- Columns deliberately mirror nutrient_reference's, so layering a user's
-- overrides over the population defaults is a plain dict update in
-- retrieval.effective_targets. Upsert on (user_id, nutrient), following the
-- user_exercise_difficulty pattern.
--
-- Nothing writes this table yet: the daily goal is currently the PHE baseline
-- for the user's sex/age. It exists so the goal-setting flow (cut/maintain/bulk)
-- has somewhere to land without a second migration.
CREATE TABLE user_nutrition_targets (
  "user_id"    integer     NOT NULL REFERENCES "user"("user_id"),
  "nutrient"   varchar(20) NOT NULL,
  "value"      real        NOT NULL,
  "limit_type" varchar(6)  NOT NULL,
  PRIMARY KEY ("user_id", "nutrient")
);
