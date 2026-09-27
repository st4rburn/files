import logging
import mimetypes
from pathlib import Path
from typing import Annotated, BinaryIO

from fastapi.responses import RedirectResponse, StreamingResponse
import uvicorn
from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, dependencies
from .config import CONFIG, ShareConfig
from .models import AuthBackend, PermissionDenied, ShareACL, User
from .filesystem import File, Folder, FolderType, file_chunk_generator

app = FastAPI(root_path="")
templates = Jinja2Templates(directory="templates")


# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(CONFIG.main.site_root)],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=CONFIG.main.session_secret)

# Include routers
api = APIRouter(prefix=CONFIG.api.path, tags=["api"])
api.mount("/static", StaticFiles(directory="static"), name="static")
api.include_router(auth.router)

app.include_router(api)

def css_classifier(obj: Folder | File) -> str:
    if isinstance(obj, File):
        return "file"
    elif obj.type == FolderType.SHARE:
        return "share"
    elif obj.type == FolderType.VIRTUAL:
        return "virtual"
    else:
        return "physical"

def html_error(json_mode: bool, request: Request, status: int, user: User, path: Path, message: str):
    if json_mode:
        raise HTTPException(status, message)
    else:
        return templates.TemplateResponse(request, "error.html", {
            "message": message,
            "user": user,
            "path": "/" + str(path),
            "conf": CONFIG.web,
            "api_path": CONFIG.api.path,
            "AuthBackend": AuthBackend
        }, status)

# Needs JSON cover for:
# folder, file - success
@app.get("/{path:path}")
def browse(
    request: Request,
    path: Path,
    user: Annotated[User, Depends(dependencies.eval_auth)],
    obj: Annotated[Folder | File | FileNotFoundError, Depends(dependencies.resolve_path)],
    json_mode: Annotated[bool, Depends(dependencies.json_mode)],
):
    try:
        if isinstance(obj, FileNotFoundError):
            raise obj
        if isinstance(obj, Folder):
            items = obj.op_list(user)
            if json_mode:
                # NEEDS TESTING
                return items
            else:
                return templates.TemplateResponse(request, "list.html", {
                    "parent": obj.parent,
                    "obj": obj,
                    "path": obj.path,
                    "items": items,
                    "classify": css_classifier,
                    # Required for header
                    "user": user,
                    "conf": CONFIG.web,
                    "api_path": CONFIG.api.path,
                    "AuthBackend": AuthBackend
                })
        else:
            # File
            fd: BinaryIO = obj.op_download(user)
            mime: str | None
            mime, _ = mimetypes.guess_file_type(obj.real_path)
            headers = {
                "Content-Disposition": f'attachment; filename="{obj.path.name}"'
            }
            return StreamingResponse(
                file_chunk_generator(fd),
                media_type=mime,
                headers=headers
            )
    except PermissionDenied as e:
        return html_error(json_mode, request, status.HTTP_403_FORBIDDEN, user, path, str(e))
    except FileNotFoundError:
        return html_error(json_mode, request, status.HTTP_404_NOT_FOUND, user, path, f"File not found at '/{path}'.")

# A success is 201 in this case
# Covered for JSON and HTML
@app.post("/{path:path}", status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request,
    file: UploadFile,
    path: Path,
    user: Annotated[User, Depends(dependencies.eval_auth)],
    obj: Annotated[Folder | File | FileNotFoundError, Depends(dependencies.resolve_path)],
    json_mode: Annotated[bool, Depends(dependencies.json_mode)],
):
    try:
        if isinstance(obj, FileNotFoundError):
            raise obj
        elif isinstance(obj, File):
            return html_error(json_mode, request, status.HTTP_400_BAD_REQUEST, user, path, "Cannot call upload on a file.")
        name: str = file.filename if file.filename is not None else "unknown"
        await obj.op_upload(user, name, file)
    except PermissionDenied as e:
        return html_error(json_mode, request, status.HTTP_403_FORBIDDEN, user, path, str(e))
    except FileNotFoundError:
        return html_error(json_mode, request, status.HTTP_404_NOT_FOUND, user, path, f"Folder not found at '/{path.parent}'.")
    except FileExistsError:
        return html_error(json_mode, request, status.HTTP_409_CONFLICT, user, path, f"File already exists at '/{path}'.")

    if json_mode:
        return None
    else:
        return RedirectResponse("/" + str(path), status.HTTP_303_SEE_OTHER)


# Covered for JSON, HTML (browser request) not possible
@app.delete("/{path:path}")
def delete(
    user: Annotated[User, Depends(dependencies.eval_auth)],
    obj: Annotated[Folder | File | FileNotFoundError, Depends(dependencies.resolve_path)],
    json_mode: Annotated[bool, Depends(dependencies.json_mode)],
):
    try:
        if isinstance(obj, FileNotFoundError):
            raise obj
        obj.op_delete(user)
    except PermissionDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

@app.patch("/{path:path}")
def move(
    user: Annotated[User, Depends(dependencies.eval_auth)],
    obj: Annotated[Folder | File | FileNotFoundError, Depends(dependencies.resolve_path)],
    new_path: Annotated[Path, Body(embed=True)],
    json_mode: Annotated[bool, Depends(dependencies.json_mode)],
):
    try:
        if isinstance(obj, FileNotFoundError):
            raise obj
        obj.op_move(user, new_path)
    except PermissionDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

def main():
    uvicorn.run("files:app", host="0.0.0.0", port=8000, reload=True, log_level="debug", proxy_headers=True, forwarded_allow_ips="*")
