from __future__ import annotations

from functools import cached_property
import logging
import os
import re
import secrets
from datetime import timedelta

import requests
import tomllib
from pathlib import Path
from pydantic import BaseModel, DirectoryPath, Field, FilePath, field_validator, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated, Self

from .models import ShareACL, SharePerms, ShareConfig, User

CONFIG_FILE: str = "config.toml"

ONLY_OS_ENV: bool = os.getenv("NO_CONFIG_FILE") is not None

_SLASH_DEDUPE: re.Pattern = re.compile("/+")

STATIC_CSS: Path = Path("static/extra/css")
STATIC_JS: Path = Path("static/extra/js")

class ApiConfig(BaseModel):
    recovery_token: str | None = None
    path: str = "/_"


class OidcConfig(BaseModel):
    issuer: HttpUrl
    client_id: str
    scopes: str = "openid profile email"
    groups_claim: str = "groups"
    roles_claim: str = "roles"
    username_claim: str = "preferred_username"

    private__well_known_url: HttpUrl | None = Field(
        alias="well_known_url", default=None
    )
    private__authorization_endpoint: HttpUrl | None = Field(
        alias="authorization_endpoint", default=None
    )
    private__token_endpoint: HttpUrl | None = Field(
        alias="token_endpoint", default=None
    )
    # _revocation_endpoint: HttpUrl | None = Field(alias="revocation_endpoint", default=None)
    private__end_session_endpoint: HttpUrl | None = Field(
        alias="end_session_endpoint", default=None
    )
    private__jwks_uri: HttpUrl | None = Field(alias="jwks_uri", default=None)

    @property
    def well_known_url(self) -> HttpUrl:
        if self.private__well_known_url is not None:
            return self.private__well_known_url
        return HttpUrl(
            str(self.issuer).rstrip("/") + "/.well-known/openid-configuration"
        )

    def model_post_init(self, __context):
        well_known: dict = {}

        # Try get well-known config
        r: requests.Response = requests.get(str(self.well_known_url))
        if r.ok:
            # If the URL is there and readable, convert to JSON
            # Fine to throw error if this fails, this URL should
            # have a standard JSON response
            well_known = r.json()

        # This ensures all values are covered
        # Allows us to confidently create properties that
        # do not return None.
        for key in (
            "authorization_endpoint",
            "token_endpoint",
            "end_session_endpoint",
            "jwks_uri",
        ):
            value: HttpUrl | None = getattr(self, "private__" + key)
            if value is None:
                if key in well_known:
                    setattr(self, "private__" + key, well_known[key])
                else:
                    raise ValueError(
                        f"Could not find '{key}' under OIDC config. Either '{self.well_known_url}' does not resolve or does not contain this value. Please specify manually or fix well-known URL."
                    )

    @property
    def authorization_endpoint(self) -> HttpUrl:
        assert self.private__authorization_endpoint is not None
        return self.private__authorization_endpoint

    @property
    def token_endpoint(self) -> HttpUrl:
        assert self.private__token_endpoint is not None
        return self.private__token_endpoint

    @property
    def end_session_endpoint(self) -> HttpUrl:
        assert self.private__end_session_endpoint is not None
        return self.private__end_session_endpoint

    @property
    def jwks_uri(self) -> HttpUrl:
        assert self.private__jwks_uri is not None
        return self.private__jwks_uri

class AuthConfig(BaseModel):
    oidc: OidcConfig | None = None

class WebButtonsConfig(BaseModel):
    delete: str = "delete"
    rename: str = "rename"
    download: str = "download"
    # Capitals standard for top nav items
    mkdir: str = "New Folder"

class WebConfig(BaseModel):
    buttons: WebButtonsConfig = Field(default_factory=WebButtonsConfig)
    default_style: bool = True
    extra_styles: list[Path] = []
    default_script: bool = True
    extra_scripts: list[Path] = []
    extra_head: str | None = None

    @classmethod
    def ensure_files(cls, path: Path, base: Path) -> None:
        if path.is_absolute() or not (base / path).is_file():
            raise ValueError(f"Path must be a real file relative to app's '{base}'")

    @field_validator("extra_styles")
    @classmethod
    def validate_style_paths(cls, paths: list[Path]) -> list[Path]:
        for path in paths:
            cls.ensure_files(path, STATIC_CSS)
        return paths

    @field_validator("extra_scripts")
    @classmethod
    def validate_script_paths(cls, paths: list[Path]) -> list[Path]:
        for path in paths:
            cls.ensure_files(path, STATIC_JS)
        return paths

    # Helpers for passing into page renderer
    @property
    def custom_css_base(self) -> str:
        return str(STATIC_CSS)
    @property
    def custom_js_base(self) -> str:
        return str(STATIC_JS)

class MainConfig(BaseModel):
    site_root: HttpUrl
    share_root: DirectoryPath = Path("/shares")

    session_secret: str# = Field(default=secrets.token_hex(32)) # Don't use a factory; must be consistent
    debug: bool = False

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    web: WebConfig = Field(default_factory=WebConfig)
    main: MainConfig
    api: ApiConfig = Field(default_factory=ApiConfig) # Instantiate using all defaults, will succeed here
    auth: AuthConfig = Field(default_factory=AuthConfig)

    share: list[ShareConfig] = Field(default_factory=list)

    @field_validator("share", mode="after")
    @classmethod
    def clean_path(cls, shares: list[ShareConfig]) -> list[ShareConfig]:
        paths: set[Path] = set()
        for share in shares:
            if share.path in paths:
                raise ValueError(f"Multiple shares with path '{share.path}'")
            else:
                paths.add(share.path)
        return shares

    @property
    def api_root(self) -> str:
        # Something like '/testing///path//' should end up as 'testing/path'
        offset: str = re.sub(_SLASH_DEDUPE, "/", self.api.path.strip("/"))
        return str(self.main.site_root) + "/" + offset + "/"

CONFIG: Config
if not ONLY_OS_ENV:
    with open(CONFIG_FILE, "rb") as f:
        preexisting: dict = tomllib.load(f)
        CONFIG = Config(**preexisting)
else:
    CONFIG = Config()  # pyright: ignore[reportCallIssue]
