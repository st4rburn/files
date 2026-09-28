import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth
from .config import CONFIG, ShareConfig
from .filesystem import FILESYSTEM, File, Folder
from .models import ShareACL, User

# Get authorisation from either bearer token or session
def eval_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None
) -> User: # pyright: ignore [reportArgumentType]
    session_user: User | None = request.session.get("user")
    if session_user is not None:
        return User.model_validate(session_user)
    elif authorization is not None and authorization.lower().startswith("bearer "):
        bearer: str = authorization[len("bearer "):]
        return auth.get_user_from_token(bearer)

    return auth.get_user_from_token(None)

async def resolve_path(path: Path) -> Folder | File | FileNotFoundError:
    try:
        return FILESYSTEM.tree.resolve(path)
    except FileNotFoundError as e:
        return e

async def resolve_parent(path: Path) -> Folder | FileNotFoundError:
    try:
        folder: Folder | File = FILESYSTEM.tree.resolve(path.parent)
    except FileNotFoundError as e:
        return e
    assert isinstance(folder, Folder)
    return folder

def json_mode(accept: Annotated[str | None, Header()] = None) -> bool:
    if accept is None:
        return True
    parsed: list[tuple[str, float]] = []
    for part in accept.split(","):
        if ";" in part:
            params: list[str] = part.split(";")
            name: str = params[0]
            prio: float = 1.0 # Default
            params = params[1:]
            for param in params:
                if param.count("=") != 1:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad 'Accept' header.")
                if param.startswith("q="):
                    raw_prio: str = param[2:]
                    try:
                        prio = float(raw_prio)
                    except ValueError:
                        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad 'Accept' header.")
            parsed.append((name, prio))
        else:
            parsed.append((part, 1.0))

    # Try match based on first preference
    parsed.sort(key=lambda x: x[1], reverse=True)
    for mime, _ in parsed:
        if mime in ("text/html", "application/xhtml+xml", "application/xml"):
            return False
        elif mime == "application/json":
            return True

    # There is an accept header but JSON is not in it
    # HTML is also not in it, but this may be a weird browser
    # Either way JSON was explicitly not asked for, and a
    # developer is more likely to be able to debug that
    # than a browser user
    return False
