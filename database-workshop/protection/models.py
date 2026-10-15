from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Permissions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    salary_scope: Literal["none", "self", "company", "all"] = "none"
    profit_scope: Literal["none", "company", "all"] = "none"
    company_ids: list[int] = Field(default_factory=list, max_length=50)
    can_view_pii: bool = False
    can_manage_users: bool = False
    can_view_audit: bool = False
    active: bool = True

    @model_validator(mode="after")
    def require_scope(self):
        if any(value <= 0 for value in self.company_ids) or len(set(self.company_ids)) != len(self.company_ids):
            raise ValueError("Company IDs must be unique positive integers")
        if (self.salary_scope == "company" or self.profit_scope == "company") and not self.company_ids:
            raise ValueError("Company-scoped permissions require assigned companies")
        return self


class NewUser(Permissions):
    username: str = Field(pattern=r"^[a-z][a-z0-9_]{2,31}$")
    password: SecretStr = Field(min_length=12, max_length=128)
    person_id: int | None = Field(default=None, gt=0)
