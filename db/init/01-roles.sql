-- Runs once, on first container start, as the POSTGRES_USER (annos = owner).
--
-- Two roles, because the email quarantine is a database grant rather than
-- column encryption:
--
--   annos       owner. Runs Alembic, and is the role Better Auth's CLI uses.
--   annos_api   runtime. What the Python API connects as. Gets DML on Annos'
--               own tables and nothing else — in particular no SELECT on
--               Better Auth's `user` table, where the email lives.
--
-- Deliberately NOT using ALTER DEFAULT PRIVILEGES: it would grant annos_api
-- access to every future table the owner creates, which would include Better
-- Auth's tables and silently undo the quarantine. Grants are explicit instead,
-- in db/grants.sql, applied after migrations.

CREATE ROLE annos_api LOGIN PASSWORD 'annos';

GRANT CONNECT ON DATABASE annos TO annos_api;
GRANT USAGE ON SCHEMA public TO annos_api;
