# Evidentia database migrations

Alembic is the migration runner, while each bounded context owns its version directory and every table it creates. The schemas context owns `schemas/versions/` and the PostgreSQL namespace `evidentia_schemas`.

Migrations must remain self-contained rather than importing current ORM models. Before a release they must support a tested downgrade. After release, committed migration history is append-only and production recovery uses a forward migration.
