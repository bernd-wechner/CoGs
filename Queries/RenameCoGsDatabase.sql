SELECT *
FROM pg_stat_activity
WHERE datname = 'CoGs';

SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE datname = 'CoGs';

DROP DATABASE IF EXISTS "CoGs_OLD";

ALTER DATABASE "CoGs" RENAME TO "CoGs_OLD";