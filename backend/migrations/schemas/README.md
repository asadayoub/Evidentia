# Schemas bounded-context migrations

This directory is owned only by `evidentia.modules.schemas`. Its revisions may create and change objects in `evidentia_schemas`; they must not read from, write to, or create foreign keys into another bounded context's tables.
