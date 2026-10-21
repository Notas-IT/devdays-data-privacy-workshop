"""Presenter solution for all four columns added by the existing migrations."""

from copy import deepcopy

from preprod_schema import SCHEMA as BASELINE, TARGET_SCHEMA, VIEWER_ROLE
from schema_contract import Column, keep, null

SCHEMA = deepcopy(BASELINE)
SCHEMA["people"].columns.update({
    "emergency_contact_email": Column("emergency_contact_email", "text", null(), nullable=True),
    "favorite_color": Column("favorite_color", "text", keep(domain={"red", "green", "blue"}), nullable=True),
    "internal_memo": Column("internal_memo", "text", null(), nullable=True),
    "payload": Column("payload", "jsonb", null(), nullable=True),
})
