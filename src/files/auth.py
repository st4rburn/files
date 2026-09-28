import asyncio
from typing import Any
import requests
from authlib.common.security import generate_token
from authlib.integrations.starlette_client import OAuth
from authlib.jose import jwt, JsonWebToken, KeySet
from authlib.jose.errors import JoseError
from authlib.oidc.core import CodeIDToken
from cachetools import TTLCache, cached
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from .config import CONFIG
from .models import AuthBackend, AuthenticatedUser, User

oauth: OAuth = OAuth()

type JwksResponse = dict[str, list[dict[str, str | list[str]]]]
OIDC_PUBKEYS: JwksResponse = {"keys": []}

# 192.168.2.32:8000/_/auth/login

# Set up staff realm
if CONFIG.auth.oidc is not None:
    # authorize_url = authorization_endpoint
    # access_token_url = token_endpoint
    # = revocation_endpoint
    # = end_session_endpoint
    # = userinfo_endpoint
    oauth.register(
        name="primary",
        client_id=CONFIG.auth.oidc.client_id,
        access_token_url=str(CONFIG.auth.oidc.token_endpoint),
        access_token_params=None,
        authorize_url=str(CONFIG.auth.oidc.authorization_endpoint),
        #authorize_params=None,
        api_base_url=str(CONFIG.auth.oidc.issuer),
        client_kwargs={
            "scope": CONFIG.auth.oidc.scopes,
            "code_challenge_method": "S256"
        },
        server_metadata_url=str(CONFIG.auth.oidc.well_known_url),
    )

    initial_keys: JwksResponse = requests.get(str(CONFIG.auth.oidc.jwks_uri)).json()
    OIDC_PUBKEYS["keys"].clear()
    OIDC_PUBKEYS["keys"].extend(initial_keys["keys"])


def get_user_from_token(token: str | None) -> User:
    if token is None:
        return User(details=None, backend=AuthBackend.NONE)
    elif token == CONFIG.api.recovery_token:
        # Purely symbolic in this case, recovery admin bypasses ACLs
        return User(details=None, backend=AuthBackend.RECOVERY)
    # TODO: OIDC support here
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request, next: str = "/"):
    assert CONFIG.auth.oidc is not None

    if "user" in request.session:
        request.session.pop("user")
    request.session["next"] = next

    code_verifier: str = generate_token(48)

    redirect_uri = request.url_for("auth")
    return await oauth.primary.authorize_redirect( # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        request,
        redirect_uri,
        code_challenge_method="S256",
        code_verifier=code_verifier
    )

@router.get("/logout")
async def logout(request: Request, next: str = "/"):
    if "user" in request.session:
        request.session.pop("user")
    return RedirectResponse(url=next)

@router.get("/auth")
async def auth(request: Request):
    assert CONFIG.auth.oidc is not None

    if "user" in request.session:
        return RedirectResponse(url="/")

    #code_verifier: str = request.session.pop("pkce_code_verifier", None) # pyright: ignore[reportAny]
    token: dict[str, str] = await oauth.primary.authorize_access_token( # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        request
    )
    idt: str | None = token.get("id_token")
    if idt is None:
        return "No ID token in response."

    claims = jwt.decode(idt, key=OIDC_PUBKEYS, claims_cls=CodeIDToken)
    claims.validate()

    username: str = claims[CONFIG.auth.oidc.username_claim] if CONFIG.auth.oidc.username_claim in claims else claims["sub"]
    dn: str
    if "name" in claims:
        dn = claims["name"]
    elif "given_name" in claims:
        dn = claims["given_name"]
        if "family_name" in claims:
            dn += " " + claims["family_name"]
    else:
        dn = username
    authed: AuthenticatedUser = AuthenticatedUser(id=claims["sub"], username=username, display_name=dn)
    user: User = User(backend=AuthBackend.OIDC, details=authed)
    request.session["user"] = user.model_dump(mode="json")

    next: str = "/"
    if "next" in request.session:
        next = request.session.pop("next")
    return RedirectResponse(url=next)
