-- Run as the owner (annos) AFTER `alembic upgrade head`, and again after any
-- migration that adds a table. Grants are enumerated rather than inherited via
-- ALTER DEFAULT PRIVILEGES, so that Better Auth's tables never pick them up.
--
-- If you add a table and forget to add it here, the API gets a permission error
-- on first use — noisy, which is the correct failure direction.

GRANT SELECT, INSERT, UPDATE, DELETE ON
    user_profile,
    foods,
    serving_units
TO annos_api;

GRANT USAGE, SELECT ON
    foods_id_seq,
    serving_units_id_seq
TO annos_api;

-- Belt and braces. Better Auth's tables are created by its own CLI, so they may
-- not exist yet the first time this runs; the DO block keeps that from erroring.
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'user', 'session', 'account', 'verification',
        'oauthApplication', 'oauthAccessToken', 'oauthConsent'
    ]
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = t) THEN
            EXECUTE format('REVOKE ALL ON %I FROM annos_api', t);
        END IF;
    END LOOP;
END $$;
