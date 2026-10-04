from __future__ import annotations

from collections.abc import Generator
from enum import auto, Enum
from functools import cached_property
from pathlib import Path
from typing import BinaryIO
from fastapi import UploadFile
from pydantic import BaseModel, Field

from .config import CONFIG
from .models import PermissionDenied, ShareACL, ShareConfig, SharePerms, User

class FilesystemError(Exception):
    pass

class FolderType(Enum):
    VIRTUAL = auto()
    SHARE = auto()
    PHYSICAL = auto()

# TODO: write operations as part of folder
# XD - list (see dotfiles?) - untested (but surely)
# FX - download - untested
# FD - rename/mkdir (can we do actual move?) - untested
# FD - delete (only physical can be deleted) - untested
# XD - upload - untested

# list/download: GET
# rename: PATCH
# mkdir: PUT (idempotent)
# delete: DELETE
# upload: POST

class File(BaseModel):
    folder: Folder
    name: str

    @property
    def path(self) -> Path:
        return self.folder.path / self.name

    # This will produce issues if files do not directly belong to
    # their parents, we should always make sure they do
    # Should be achievable as they should not be instantiated often
    @property
    def real_path(self) -> Path:
        return self.folder.real_path / self.path_components[-1]

    @property
    def path_components(self) -> list[str]:
        return self.folder.path_components + [self.name]

    def ensure_allowed(self, user: User, test: ShareACL):
        acl: ShareACL = self.folder.share.perms.evaluate(user)
        if test not in acl:
            if ShareACL.LIST not in acl:
                raise FileNotFoundError(f"File not found at '{self.path.parent}'.")
            else:
                raise PermissionDenied(user, test, self.path_components)

    def can_move(self, user: User) -> bool:
        _ = self.real_path
        acl: ShareACL = self.folder.share.perms.evaluate(user)
        return ShareACL.MOVE in acl

    # This is a lot simpler to rename
    def op_move(self, user: User, new_path: Path) -> None:
        # Essential checks:
        # 1. We are allowed to move FROM this folder
        # 2. We are moving into a folder
        # 3. IF FOLDER EXTERNAL TO SHARE
        #   1. Are we allowed to delete from origin share?
        #   2. Are we allowed to move and upload in destination?
        # 4. Does this file exist in the destination as a share or file?
        self.ensure_allowed(user, ShareACL.MOVE)

        # Ensure we're moving to a folder
        new_parent: Folder | File = FILESYSTEM.tree.resolve(new_path.parent)
        if isinstance(new_parent, File):
            raise FileExistsError("Would-be parent folder is a file.")

        # Check if user can move to this share, requires move|upload perm
        if new_parent.share != self.folder.share:
            new_parent.ensure_allowed(user, ShareACL.MOVE | ShareACL.UPLOAD)
            self.ensure_allowed(user, ShareACL.REMOVE)

        # Make sure parent doesn't have any child shares with this
        # name or any folders
        new_name: str = new_path.name
        if new_path.exists() or new_name in new_parent.children:
            raise FileExistsError("Share or folder already exists with this path")

        # Do the move
        self.real_path.rename(new_parent.real_path / new_name)
        self.folder = new_parent
        self.name = new_name

    def can_delete(self, user: User) -> bool:
        _ = self.real_path
        acl: ShareACL = self.folder.share.perms.evaluate(user)
        return ShareACL.REMOVE in acl

    def op_delete(self, user: User) -> None:
        real: Path = self.real_path
        self.ensure_allowed(user, ShareACL.REMOVE)
        real.unlink()

    def can_download(self, user: User) -> bool:
        _ = self.real_path
        acl: ShareACL = self.folder.share.perms.evaluate(user)
        return ShareACL.DOWNLOAD in acl

    def op_download(self, user: User) -> BinaryIO:
        real: Path = self.real_path
        self.ensure_allowed(user, ShareACL.DOWNLOAD)
        return real.open("rb")

class Folder(BaseModel):
    share: ShareConfig
    # This is made from ShareConfig's path_components
    path_components: list[str]
    # Whether this was created manually or to fill the tree
    type: FolderType
    children: dict[str, Folder] = Field(default_factory=dict)

    @property
    def real_path(self) -> Path:
        return self.get_real_path(self.path_components, traverse=False)

    @property
    def path(self) -> Path:
        return Path("/", *self.path_components)

    @property
    def parent(self) -> Folder:
        # Get parent, this is probably expensive but should be rare
        parent: Folder | File = FILESYSTEM.tree.resolve(self.path_components[:-1])
        # This cannot be a file, it's our path but up one
        assert isinstance(parent, Folder)
        return parent

    def ensure_allowed(self, user: User, test: ShareACL):
        acl: ShareACL = self.share.perms.evaluate(user)
        if test not in acl:
            if ShareACL.LIST not in acl:
                raise FileNotFoundError(f"File not found at '{self.path.parent}'.")
            else:
                raise PermissionDenied(user, test, self.path_components)

    def can_download(self, user: User) -> bool:
        return False

    def can_list(self, user: User) -> bool:
        # If we're trying to get a path that's not within the share
        # this will throw an error
        _ = self.real_path
        acl: ShareACL = self.share.perms.evaluate(user)
        return ShareACL.LIST in acl

    def op_list(self, user: User) -> Generator[Folder | File]:
        # If we're trying to get a path that's not within the share
        # this will throw an error
        _ = self.real_path
        self.ensure_allowed(user, ShareACL.LIST)
        dotfiles: bool = ShareACL.DOTFILES in self.share.perms.evaluate(user)

        # For quicker comparison
        my_share: ShareConfig = self.share
        for item in self.get_items(dotfiles, sort=True):
            # If this user doesn't have list permissions on the share
            # we're looking at now, make it invisible
            if isinstance(item, Folder) and item.share != my_share:
                acl: ShareACL = item.share.perms.evaluate(user)
                if ShareACL.LIST not in acl:
                    continue
            yield item

    def can_mkdir(self, user: User) -> bool:
        _ = self.real_path
        acl: ShareACL = self.share.perms.evaluate(user)
        return ShareACL.MOVE in acl

    def op_mkdir(self, user: User, name: str) -> None:
        real: Path = self.real_path
        self.ensure_allowed(user, ShareACL.MOVE)
        if "/" in name:
            raise ValueError("Folder name cannot contain '/'.")
        new: Path = real / name
        if new.exists():
            raise FileExistsError()
        new.mkdir()

    def can_move(self, user: User) -> bool:
        if self.type != FolderType.PHYSICAL:
            return False
        _ = self.real_path
        acl: ShareACL = self.share.perms.evaluate(user)
        return ShareACL.MOVE in acl

    def op_move(self, user: User, new_path: Path) -> None:
        # Essential checks:
        # 1. This is a physical folder
        # 2. We are allowed to move FROM it
        # 3. We are moving into a folder
        # 4. IF FOLDER EXTERNAL TO SHARE
        #   1. Are we allowed to delete from origin share?
        #   2. Are we allowed to move and upload in destination?
        # 5. Does this file exist in the destination as a share or file?
        if self.type != FolderType.PHYSICAL:
            raise FilesystemError(f"Folder of type {self.type} cannot be renamed.")
        # Ensure we can move this folder
        self.ensure_allowed(user, ShareACL.MOVE)

        # Ensure we're moving to a folder
        new_parent: Folder | File = FILESYSTEM.tree.resolve(new_path.parent)
        if isinstance(new_parent, File):
            raise FileExistsError("Would-be parent folder is a file.")

        # Check if user can move to this share, requires move|upload perm
        if new_parent.share != self.share:
            new_parent.ensure_allowed(user, ShareACL.MOVE | ShareACL.UPLOAD)
            self.ensure_allowed(user, ShareACL.REMOVE)

        # Make sure parent doesn't have any child shares with this
        # name or any folders
        new_name: str = new_path.name
        if new_path.exists() or new_name in new_parent.children:
            raise FileExistsError("Share or folder already exists with this path")

        self.real_path.rename(new_parent.real_path / new_name)
        self.path_components.clear()
        self.path_components += Folder.neat_path(new_path)

    def can_delete(self, user: User) -> bool:
        if self.type != FolderType.PHYSICAL:
            return False
        _ = self.real_path
        acl: ShareACL = self.share.perms.evaluate(user)
        return ShareACL.REMOVE in acl

    # TODO: by messing with real path locations in the config is it then possible to accidentially
    # delete a higher real path that isn't seen as a share?
    # FIX: Maybe stop explicitly defined real paths from being within or above the share root
    def op_delete(self, user: User) -> None:
        if self.type != FolderType.PHYSICAL:
            raise FilesystemError(f"Folder of type {self.type} cannot be deleted.")
        real: Path = self.real_path
        self.ensure_allowed(user, ShareACL.REMOVE)
        for item in self.get_items():
            item.op_delete(user)
        real.rmdir()

    def can_upload(self, user: User) -> bool:
        _ = self.real_path
        acl: ShareACL = self.share.perms.evaluate(user)
        return ShareACL.UPLOAD in acl

    async def op_upload(self, user: User, name: str, file: UploadFile) -> None:
        real: Path = self.real_path
        self.ensure_allowed(user, ShareACL.UPLOAD)
        if "/" in name:
            raise ValueError("Folder name cannot contain '/'.")
        new: Path = real / name
        if new.exists():
            raise FileExistsError()
        with new.open("wb+") as f:
            while True:
                chunk: bytes = await file.read(4096)
                if not chunk:
                    break
                f.write(chunk)

    def get_items(self, dotfiles: bool = False, sort: bool = False) -> Generator[Folder | File]:
        generator: Generator[Path] | list[Path] = self.real_path.iterdir()
        # This takes more time but is better for display
        if sort:
            # Directories first (False = 0), then alphabetical
            generator = sorted(generator, key=lambda path: (not path.is_dir(), path.name))
        for item in generator:
            if item.is_dir():
                if item.name in self.children:
                    yield self.children[item.name]
                else:
                    yield Folder(
                        share=self.share,
                        path_components=self.path_components + [item.name],
                        type=FolderType.PHYSICAL,
                    )
            elif item.is_file():
                if item.name.startswith(".") and not dotfiles:
                    continue
                yield File(
                    folder=self,
                    name=item.name
                )
            else:
                # Ignore special files
                continue

    def get_real_path(self, path: Path | list[str], traverse: bool = True) -> Path:
        path = Folder.neat_path(path)
        folder: Folder
        if traverse:
            # Get the deepest share so real path will be accurate
            folder = self.get_deepest_share(path)
        else:
            folder = self
        str_path: str = "/" + "/".join(path)
        for my_part, req_part in zip(folder.share.path_components, path):
            if my_part != req_part:
                raise FilesystemError(f"Path '{str_path}' is not under '{folder.share.path}'.")
        addtional_hops: int = len(path) - len(folder.share.path_components)
        if addtional_hops < 0:
            raise FilesystemError(f"Path '{str_path}' is shorter than share path '{folder.share.path}'.")

        extra: list[str] = []
        if addtional_hops != 0:
            # list[-0:] becomes index 0 to end, whole array
            # It should be none of the array
            extra = path[-addtional_hops:]
        real: Path = share_real_path(folder.share)
        real /= Path(*extra)
        return real

    @staticmethod
    def neat_path(path: Path | list[str]) -> list[str]:
        # Convert path to list first
        if isinstance(path, Path):
            old_parts: list[str] = list(path.parts)
            if old_parts and old_parts[0] == "/":
                _ = old_parts.pop(0)
            path = old_parts

        # Filter out .. and . before they can be allowed on the filesystem
        # Also process '/'
        fixed: list[str] = []
        for part in path:
            if part == ".":
                continue
            elif part == "..":
                if fixed:
                    _ = fixed.pop(-1)
                else:
                    continue
            elif part.startswith("/"):
                # '/' sends us back to the root
                fixed.clear()
                # Trim them off, do we have other pieces?
                trimmed: str = part.strip("/")
                if not trimmed:
                    # No, keep going
                    continue
                # This should not be allowed or possible, but
                # if it happens could be a security issue
                raise ValueError("Part of path contained '/' after trimming, has a string path been included in a Path object?")
            else:
                fixed.append(part)
        return fixed

    def get_deepest_share(self, path: Path | list[str]) -> Folder:
        path = Folder.neat_path(path)

        node: Folder = self
        for part in path:
            if part in node.children:
                node = node.children[part]
            else:
                break
        return node

    def resolve(self, path: Path | list[str]) -> Folder | File:
        path = Folder.neat_path(path)

        # This deals with shares/virtual folders
        share: Folder = self.get_deepest_share(path)
        if share.path_components == path:
            return share

        # No need to traverse, we already did
        real: Path = share.get_real_path(path, traverse=False)
        # Based on whether this is a file or dir, return the
        # right object
        # Special files not supported
        if real.is_dir():
            return Folder(
                share=share.share,
                path_components=path,
                type=FolderType.PHYSICAL,
            )
        elif real.is_file():
            parent: Folder = Folder(
                share=share.share,
                path_components=path[:-1],
                type=FolderType.PHYSICAL,
            )
            return File(
                folder=parent,
                name=path[-1]
            )
        else:
            raise FileNotFoundError()


class Filesystem:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self._tree: Folder = self._gen_tree()

    @property
    def tree(self) -> Folder:
        return self._tree

    def _gen_tree(self) -> Folder:
        # Sort so that the shortest
        CONFIG.share.sort(key=lambda v: len(v.path_components))
        # Root will always be first
        root: Folder
        root_share: ShareConfig
        if CONFIG.share and CONFIG.share[0].path == Path("/"):
            root_share = CONFIG.share.pop(0)
            root = Folder(
                share=root_share,
                path_components=root_share.path_components.copy(),
                type=FolderType.SHARE
            )
        else:
            # Create blank share with no permissions if none is defined
            root_share = ShareConfig(
                path = Path("/"),
                perms = SharePerms(),
                real = CONFIG.main.share_root
            )
            root = Folder(
                share=root_share,
                path_components=[],
                type=FolderType.VIRTUAL
            )
        # Make root share if it doesn't exist (it should, shouldn't parse otherwise)
        if root.share.real is not None and not root.share.real.exists():
                root.share.real.mkdir(parents=True)
        for share in CONFIG.share:
            parent: Folder = root
            for component in share.path_components[:-1]:
                if component in parent.children:
                    parent = parent.children[component]
                else:
                    new_node: Folder = Folder(
                        share=parent.share,
                        path_components=parent.path_components + [component],
                        type=FolderType.VIRTUAL
                    )
                    new_node.real_path.mkdir(exist_ok=True, parents=True)
                    parent.children[component] = new_node
                    parent = new_node
            new_share: Folder = Folder(
                share=share,
                path_components=share.path_components,
                type=FolderType.SHARE
            )
            new_share.real_path.mkdir(exist_ok=True, parents=True)
            parent.children[share.path_components[-1]] = new_share
        return root

# Helper
def share_real_path(share: ShareConfig) -> Path:
    if share.real is not None:
        return Path(share.real)
    else:
        return Path(CONFIG.main.share_root) / Path(*share.path_components)


def file_chunk_generator(fd: BinaryIO, chunk_size: int = 1024 * 1024):
    while chunk := fd.read(chunk_size):
        yield chunk


FILESYSTEM: Filesystem = Filesystem()
