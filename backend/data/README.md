## Demo profile data

- Structure
  - `schema/profile_schema.json`: Profile JSON Schema (FieldValue wrapper + module structure).
  - `profiles/u_demo_young_male.json`: Sample profile (young male, mild obesity, high glucose tendency).
  - `logs/glucose_u_demo_young_male.jsonl`: Optional synthetic glucose readings.
  - `state/proactive_state.json`: Proactive loop state (enabled flag, cooldown timestamps).

- Storage conventions
  - Path: `backend/data/profiles/{user_id}.json`.
  - Every field uses `FieldValue`: `{ value, layer, confidence, source, updated_at, revoked }`.
    - `layer`: `confirmed` or `inferred`.
    - `confidence`: 0~1 (use lower values for inferred).
    - `source`: short provenance like `user_edit` / `ai_infer` / `seed`.
    - `updated_at`: ISO8601 UTC.
    - `revoked`: whether the field is invalidated.

- Editing & APIs
  - You can edit `profiles/*.json` directly; keep schema hierarchy and FieldValue shape.
  - PATCH API supports path syntax (e.g., `diet.sweet_drink_pref`) and wraps into FieldValue automatically.
  - Revoke API marks the field `revoked=true` and refreshes `updated_at`.

- Dependencies
  - Added `openai` (used by proactive trigger to generate user queries).
  - If you later need schema validation, add `jsonschema` and wire it in `profile_store.py`.
