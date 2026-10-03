# Local development

## Native PostgreSQL workflow

Evidentia currently supports native PostgreSQL 16.x for ordinary development. Docker is optional and its equivalent development profile is deferred to `TASK-008` near the end of product development.

Generate a private environment file once:

```sh
make local-init
```

The generator refuses to overwrite an existing `.env`. If the file predates the native workflow, preserve any values you need, move it aside, and run `make local-init` again. Never commit `.env`.

Start and inspect Homebrew PostgreSQL:

```sh
brew services start postgresql@16
brew services info postgresql@16
```

Create the dedicated `evidentia` login and database, then verify the exact configured connection:

```sh
make native-db-init
make native-db-verify
```

Initialization is idempotent: it creates missing local objects, retains an existing database, and aligns the dedicated development role password with the private `.env`. It does not run application migrations.

Stop the database when desired:

```sh
brew services stop postgresql@16
```

## Connection contract

The application reads `EVIDENTIA_DATABASE__HOST`, `PORT`, `NAME`, `USER`, `PASSWORD`, `CONNECT_TIMEOUT_SECONDS`, `SSLMODE`, and `APPLICATION_NAME`. Local defaults use `127.0.0.1:5432`, database `evidentia`, role `evidentia`, and `sslmode=prefer`. Secrets are generated into the owner-readable ignored `.env` and are never printed by the readiness command.

## Troubleshooting

If Homebrew reports an error, inspect before changing anything:

```sh
brew services info postgresql@16
pg_isready --host=127.0.0.1 --port=5432
tail -n 100 /usr/local/var/log/postgresql@16.log
```

A `postmaster.pid already exists` message can mean either a live server or a stale file after an unclean shutdown. Confirm the recorded PID is not PostgreSQL, confirm no socket or listener exists, and use `pg_ctl status` before moving the PID file. Never delete the data directory or run `initdb` over it as a repair.

The stale PID encountered on 2026-10-03 was moved recoverably to `/tmp/evidentia-stale-postmaster.pid-20261003`; PostgreSQL performed automatic WAL recovery and returned to a ready state without data deletion.
