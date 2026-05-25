# Changelog

## Public Repository Bootstrap

- Created a clean public project copy with source code, tests, Docker setup, and
  documentation.
- Removed local runtime artifacts from the distributable tree, including
  databases, model weights, generated media, screenshots, caches, build output,
  dependency folders, and private environment files.
- Added sanitized `.env.example`, public `.gitignore`, MIT license, text-only
  starter wildcard data, and a release verification script.
- Changed the public Docker default to the lightweight backend image and dry-run
  training mode. Use `BACKEND_DOCKERFILE=Dockerfile.gpu` only after configuring
  a local GPU trainer environment.
- Removed automatic host-drive mounts from the public Compose file. Add local
  media mounts through an uncommitted `docker-compose.override.yml`.
