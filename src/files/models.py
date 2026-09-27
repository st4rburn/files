from __future__ import annotations

from enum import Enum, Flag, auto
from fastapi import Request
from functools import cached_property
from pathlib import Path
from pydantic import BaseModel, DirectoryPath, Field, field_validator, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from typing import Any, Self

PERMKEY_AUTHED_USERS: str = "AUTH"
PERMKEY_ALL_USERS: str = "ALL"
PERMKEY_SELF: str = "SELF"

class PermissionDenied(PermissionError):
    def __init__(self, user: User, perm: ShareACL, path: Path | list[str]) -> None:
        name: str
        if user.details is not None:
            name = user.details.display_name + " (" + user.details.username + ")"
        elif user.backend == AuthBackend.NONE:
            name = "<unauthenticated>"
        elif user.backend == AuthBackend.RECOVERY:
            name = "<recovery token>"
        else:
            name = "<unknown>"
        if isinstance(path, list):
            path = Path("/", *path)
        msg: str = f"User '{name}' does not have permission to perform '{perm}' at '{path}'."
        super().__init__(msg)

class ShareACL(Flag):
    NONE = 0
    LIST = auto()
    DOWNLOAD = auto()
    UPLOAD = auto()
    REMOVE = auto()
    MOVE = auto()
    DOTFILES = auto()

    @classmethod
    def parse(cls, raw: str) -> ShareACL:
        if not isinstance(raw, str):
            raise TypeError("Expected string for ACL parser.")
        result: ShareACL = ShareACL.NONE
        shorthand: dict[str, ShareACL] = {
            # Permissions
            "l": ShareACL.LIST,
            "d": ShareACL.DOWNLOAD,
            "u": ShareACL.UPLOAD,
            "r": ShareACL.REMOVE,
            "m": ShareACL.MOVE,
            ".": ShareACL.DOTFILES,
            # Special flags
            "-": ShareACL.NONE,
            "*": ~ShareACL.NONE,
        }
        for k, v in shorthand.items():
            if k in raw:
                result |= v
        return result

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        # Chain it as a 'before' validator on top of the default Enum schema
        return core_schema.no_info_before_validator_function(
            cls.parse,
            schema=handler(source)
        )

class AuthBackend(Enum):
    NONE = "none"
    RECOVERY = "recovery"
    OIDC = "oidc"

class AuthenticatedUser(BaseModel):
    id: str
    username: str
    display_name: str
    groups: list[str] = Field(default_factory=list)

class User(BaseModel):
    details: AuthenticatedUser | None
    backend: AuthBackend = AuthBackend.NONE

class SharePerms(BaseModel):
    user: dict[str, ShareACL] = Field(default_factory=dict)
    group: dict[str, ShareACL] = Field(default_factory=dict)

    # If this share exists because of a wildcard
    owning_user: str | None = None
    owning_group: str | None = None

    def evaluate(self, user: User) -> ShareACL:
        # TODO - eval authed and all perms
        result: ShareACL = ShareACL.NONE
        if user.backend == AuthBackend.RECOVERY:
            # All permissions for recovery
            return ~ShareACL.NONE

        # Permissions for all users apply to unauthed
        if PERMKEY_ALL_USERS in self.user:
            result |= self.user[PERMKEY_ALL_USERS]

        # Meaning this is an authenticated user
        if user.details is not None:
            # Add permissions for authed users
            if PERMKEY_AUTHED_USERS in self.user:
                result |= self.user[PERMKEY_AUTHED_USERS]

            # Add owner permissions
            if user.details.username == self.owning_user and PERMKEY_SELF in self.user:
                result |= self.user[PERMKEY_SELF]
            if self.owning_group in user.details.groups and PERMKEY_SELF in self.group:
                result |= self.group[PERMKEY_SELF]

            # Add permissions for the user's specific name/groups
            if user.details.username in self.user:
                result |= self.user[user.details.username]
            for group_name in user.details.groups:
                if group_name in self.group:
                    result |= self.group[group_name]

        # Return all permissions gained
        return result

class ShareConfig(BaseModel):
    title: str | None = None
    path: Path
    # Override share root
    real: DirectoryPath | None = None
    perms: SharePerms = Field(default_factory=SharePerms)

    @field_validator("path", mode="after")
    @classmethod
    def clean_path(cls, value: Path) -> Path:
        new_parts: list[str] = []
        for part in value.parts:
            if part == "..":
                raise ValueError("Path should not contain '..'.")
            if part != ".":
                new_parts.append(part)
        if new_parts and new_parts[0] != "/":
            new_parts.insert(0, "/")
        return Path(*new_parts)

    @cached_property
    def path_components(self) -> list[str]:
        parts: list[str] = list(self.path.parts)
        if parts and parts[0] == "/":
            _ = parts.pop(0)
        return parts
