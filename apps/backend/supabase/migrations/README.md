# Supabase SQL migrations

[`schema.sql`](../schema.sql) is the **greenfield** full DDL for new projects.

The SQL files in this folder are **optional upgrade paths** for databases that already ran an older schema.

| File | Purpose |
|------|---------|
| [`vital_logs_to_health_issue_events.sql`](vital_logs_to_health_issue_events.sql) | Replace legacy `vital_logs` with `health_issue_events` and copy rows as `routing_intent = 'log_vital'`. |

DBs that previously ran an older `health_issue_events` DDL (`event_type` / `recorded_at`) should align columns with current [`schema.sql`](../schema.sql) (rename/add `routing_intent`, `user_message`, `locale`, `created_at`; map `vital` → `log_vital`) before relying on classifier-intent logging.

After running a migration, verify row counts and application behavior before dropping backups.
