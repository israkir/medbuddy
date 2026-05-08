# Supabase SQL migrations

[`schema.sql`](../schema.sql) is the **greenfield** full DDL for new projects.

The SQL files in this folder are **optional upgrade paths** for databases that already ran an older schema.

| File | Purpose |
|------|---------|
| _(none currently)_ | Greenfield installs should use [`schema.sql`](../schema.sql). Add migration files here only for legacy upgrade paths. |

DBs that previously ran an older `health_issue_events` DDL (`event_type` / `recorded_at`) should align columns with current [`schema.sql`](../schema.sql) (rename/add `routing_intent`, `user_message`, `locale`, `created_at`; map `vital` → `log_vital`) before relying on classifier-intent logging.

After running a migration, verify row counts and application behavior before dropping backups.
