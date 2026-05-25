# Database Migration Helpers

This folder contains legacy one-time copy helpers for importing older Wildcard
Workshop and Movie Script data into the current Mklan Studio data directory.

The active application does not use these scripts as a general schema migration
system. Current SQLite databases are created and updated by their module startup
code.

## Current Databases

| Module | Default path |
|---|---|
| Wildcards | `data/wildcards/wildcard_workshop.db` |
| Movie | `data/movie/movie_tool.db` |
| Cards | `data/cards/card_creator.db` |

Media Indexer uses PostgreSQL under `data/postgres/` when the media-indexer
Docker profile is enabled.

## Preview A Copy

Run dry-run mode before copying data:

```powershell
cd backend
python -m migrations.migrate_wildcard --dry-run
python -m migrations.migrate_movie --dry-run
```

## Run A Copy

```powershell
cd backend
python -m migrations.migrate_wildcard
python -m migrations.migrate_movie
```

The helpers support explicit source and target paths. Check each script with
`--help` before using it against important data.

```powershell
python -m migrations.migrate_wildcard --help
python -m migrations.migrate_movie --help
```

## Safety Notes

- Back up `data/` before running copy helpers.
- Do not run these scripts against a live container that is actively writing to
  the same database.
- Prefer dry-run output first, then run the copy only after the target paths look
  correct.
