"""Load synthetic source fixtures into the student production database."""

import os
from pathlib import Path
import psycopg


def main():
    with psycopg.connect(os.environ["SOURCE_ADMIN_DSN"]) as connection:
        connection.execute(Path(__file__).with_name("schema.sql").read_text())
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO business.companies VALUES (%s, %s, %s)",
                [(i, f"Demo Company {i}", i * 98765) for i in range(1, 11)],
            )
            cursor.executemany(
                "INSERT INTO business.people VALUES (%s, %s, %s, %s, %s, %s)",
                [(i, "Demo", f"Person {i}", f"person-{i}@example.com",
                  f"390{i:08d}", "1990-01-01") for i in range(1, 1001)],
            )
            cursor.executemany(
                "INSERT INTO business.employment VALUES (%s, %s, %s, %s, %s)",
                [(i, f"person-{i}@example.com", 1 + i % 10, 2000 + i % 4000,
                  "Engineering" if i % 2 else "Sales") for i in range(1, 1001)],
            )
    print("Synthetic source fixtures loaded.")


if __name__ == "__main__":
    main()
