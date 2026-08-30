"""Pydantic UserCreate — username 3..32, password 4..128, rol admin|portero"""
from pydantic import BaseModel, Field

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(min_length=4, max_length=128)
    rol: str = Field(pattern="^(admin|portero)$")

class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=32)
    password: str | None = Field(None, min_length=4, max_length=128)
    rol: str | None = Field(None, pattern="^(admin|portero)$")
