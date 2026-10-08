# Documents migrations

This branch owns only the `evidentia_documents` PostgreSQL namespace. Original
document bytes are not stored in PostgreSQL; the tables retain tenant-scoped
custody metadata, upload attempts, integrity facts, and append-only events.
