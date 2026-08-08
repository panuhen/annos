#!/bin/bash
# Runs once, on first container start, as the POSTGRES_USER (annos = owner).
#
# Two roles, because the email quarantine is a database grant rather than
# column encryption:
#
#   annos       owner. Runs Alembic, and is the role Better Auth's CLI uses.
#               Its password is POSTGRES_PASSWORD.
#   annos_api   runtime. What the Python API connects as. Gets DML on Annos'
#               own tables and nothing else — in particular no SELECT on
#               Better Auth's `user` table, where the email lives. Its password
#               is ANNOS_API_DB_PASSWORD.
#
# Deliberately NOT using ALTER DEFAULT PRIVILEGES: it would grant annos_api
# access to every future table the owner creates, which would include Better
# Auth's tables and silently undo the quarantine. Grants are explicit instead,
# in api/db/grants.sql, applied after migrations by annos.apply_grants.
#
# Shell rather than plain SQL so the annos_api password can come from the
# environment (a strong value in production; `annos` by default for local dev
# and the test suite). psql's :'var' quoting keeps special characters safe.
set -e

psql -v ON_ERROR_STOP=1 \
  -v api_pw="${ANNOS_API_DB_PASSWORD:-annos}" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE annos_api LOGIN PASSWORD :'api_pw';
GRANT CONNECT ON DATABASE annos TO annos_api;
GRANT USAGE ON SCHEMA public TO annos_api;
SQL
