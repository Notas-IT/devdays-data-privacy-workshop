\set ON_ERROR_STOP on
SET DateStyle = 'ISO';
SET TimeZone = 'UTC';

-- Compare row contents without displaying individual values. Row order is ignored.
SELECT format(
    'SELECT %L, count(*), md5(coalesce(string_agg(row_to_json(t)::text, E''\n'' ORDER BY row_to_json(t)::text), '''')) FROM %I.%I AS t;',
    schemaname || '.' || tablename, schemaname, tablename
)
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
  AND schemaname NOT LIKE 'pg_toast%'
ORDER BY schemaname, tablename
\gexec
