"""Student-owned target schema: every output column names its input and rule.

Constants mask original values. Shared HMAC scopes preserve equality across
related columns. Keeping production IDs means this is not proven anonymity.
"""

from schema_contract import Column, ForeignKey, Table, constant, keep, token_email, token_id

TARGET_SCHEMA = "business"
VIEWER_ROLE = "preprod_viewer"

SCHEMA = {
    "companies": Table(
        source="companies",
        columns={
            "annual_profit_eur": Column("annual_profit_eur", "integer", constant(0)),
            "company_id": Column("company_id", "bigint", keep()),
            "company_name": Column("company_name", "text", constant("Synthetic Company")),
        },
        primary_key=("company_id",),
    ),
    "employment": Table(
        source="employment",
        columns={
            "company_id": Column("company_id", "bigint", keep()),
            "contract_id": Column("contract_id", "bigint", keep()),
            "department": Column("department", "text", keep()),
            "employee_email": Column("employee_email", "text", token_email("email")),
            "salary_eur": Column("salary_eur", "integer", constant(3500)),
        },
        primary_key=("contract_id",),
        foreign_keys=(
            ForeignKey(("company_id",), "companies", ("company_id",)),
            ForeignKey(("employee_email",), "people", ("email",)),
        ),
        checks=("salary_eur > 0",),
    ),
    "people": Table(
        source="people",
        columns={
            "birth_date": Column("birth_date", "date", constant("2000-01-01")),
            "email": Column("email", "text", token_email("email")),
            "first_name": Column("first_name", "text", constant("Person")),
            "last_name": Column("last_name", "text", constant("Anonymous")),
            "national_id": Column("national_id", "text", token_id("national_id")),
            "person_id": Column("person_id", "bigint", keep()),
        },
        primary_key=("person_id",),
        unique=(("email",), ("national_id",)),
    ),
}
