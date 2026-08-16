from __future__ import annotations

from typing import Literal
from pydantic import Field, field_validator
from app.contracts.base import ContractModel

AccountRole = Literal["business", "risk", "leadership"]

class LoginRequest(ContractModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

class AuthenticatedAccount(ContractModel):
    account_id: str
    username: str
    display_name: str
    role: AccountRole

class LogoutResult(ContractModel):
    logged_out: bool = True
