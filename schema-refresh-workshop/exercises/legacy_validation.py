"""Intentionally failing acceptance test after the new-columns migration."""

import pytest
from refresh import connect


@pytest.mark.parametrize("column", ["emergency_contact_email", "payload"])
def test_legacy_refresh_did_not_leak_new_sensitive_fields(column):
    from psycopg import sql
    with connect("TARGET_DSN") as target:
        count = target.execute(sql.SQL("SELECT count(*) FROM legacy.people WHERE {} IS NOT NULL").format(
            sql.Identifier(column))).fetchone()[0]
    assert count == 0, f"Legacy refresh leaked {count} rows in {column}"
