import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth
from .config import CONFIG, ShareConfig
from .filesystem import FILESYSTEM, File, Folder
from .models import ShareACL, User

def eval_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None
) -> User: # pyright: ignore [reportArgumentType]
    session_user: User | None = request.session.get("user")
    if session_user is not None:
        return User.model_validate(session_user)
    elif authorization:
        # TODO: FIX THIS
        return auth.get_user_from_token(authorization)

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
