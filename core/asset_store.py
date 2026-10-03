"""
Local asset store abstraction for WallMock catalog builds.

Defines the AssetStore protocol and a LocalAssetStore implementation
that stores files in a content-addressed directory structure:

    assets/<design_id>/<device_id>/<case_type>/<view>-<width>.<hash12>.webp

The content-addressed paths make it safe to serve directly from a
CDN — filenames change when content changes, enabling aggressive
caching.
"""
import os
import shutil
from pathlib import Path
from typing import Protocol, Optional


class AssetStore(Protocol):
    """Protocol for asset storage backends.

    Implementations provide a simple put/get/exists/delete interface
    for storing and retrieving binary asset data by path.
    """

    def put(self, asset_bytes: bytes, path: str) -> str:
        """Store asset bytes at the given relative path.

        Parameters
        ----------
        asset_bytes : bytes
            The binary data to store.
        path : str
            Relative path within the store.

        Returns
        -------
        str
            The relative path the asset was stored at.
        """
        ...

    def get(self, path: str) -> bytes:
        """Retrieve asset bytes from the given relative path.

        Parameters
        ----------
        path : str
            Relative path within the store.

        Returns
        -------
        bytes
            The binary asset data.

        Raises
        ------
        FileNotFoundError
            If the asset does not exist.
        """
        ...

    def exists(self, path: str) -> bool:
        """Check if an asset exists at the given path.

        Parameters
        ----------
        path : str
            Relative path within the store.

        Returns
        -------
        bool
            True if the asset exists.
        """
        ...

    def delete(self, path: str) -> bool:
        """Delete an asset at the given path.

        Parameters
        ----------
        path : str
            Relative path within the store.

        Returns
        -------
        bool
            True if the asset was deleted, False if it didn't exist.
        """
        ...


class LocalAssetStore:
    """Local filesystem implementation of AssetStore.

    Stores files in a root directory with the given relative paths.
    Supports content-addressed naming for cache-friendly deployments.
    """

    def __init__(self, root_dir: str):
        """Initialize the local asset store.

        Parameters
        ----------
        root_dir : str
            Root directory for the store. Will be created if it
            doesn't exist.
        """
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> str:
        """Absolute path to the store root directory."""
        return str(self._root)

    def _resolve(self, path: str) -> Path:
        """Resolve a relative path and ensure it doesn't escape the root.

        Raises ValueError if the path would escape the store root.
        """
        # Use os.path.normpath then resolve to catch all traversal attempts
        candidate = (self._root / path).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError:
            raise ValueError(
                f"Asset path '{path}' escapes the store root '{self._root}'"
            )
        return candidate

    def put(self, asset_bytes: bytes, path: str) -> str:
        """Store asset bytes at the given relative path."""
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(asset_bytes)
        return path

    def put_file(self, source_path: str, path: str) -> str:
        """Copy an existing file into the store.

        Parameters
        ----------
        source_path : str
            Path to the source file on disk.
        path : str
            Relative destination path within the store.

        Returns
        -------
        str
            The relative path the asset was stored at.
        """
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, str(full_path))
        return path

    def get(self, path: str) -> bytes:
        """Retrieve asset bytes from the given relative path."""
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Asset not found: {path}")
        with open(full_path, "rb") as f:
            return f.read()

    def get_path(self, path: str) -> str:
        """Get the absolute filesystem path for an asset.

        Parameters
        ----------
        path : str
            Relative path within the store.

        Returns
        -------
        str
            Absolute filesystem path.

        Raises
        ------
        FileNotFoundError
            If the asset does not exist.
        """
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"Asset not found: {path}")
        return str(full_path)

    def exists(self, path: str) -> bool:
        """Check if an asset exists at the given path."""
        try:
            full_path = self._resolve(path)
        except ValueError:
            return False
        return full_path.exists() and full_path.is_file()

    def delete(self, path: str) -> bool:
        """Delete an asset at the given path."""
        try:
            full_path = self._resolve(path)
        except ValueError:
            return False
        if full_path.exists() and full_path.is_file():
            full_path.unlink()
            return True
        return False

    def list_dir(self, dir_path: str = "") -> list:
        """List files in a directory within the store.

        Parameters
        ----------
        dir_path : str
            Relative directory path within the store.

        Returns
        -------
        list
            List of entry names (files and subdirectories).
        """
        full_path = self._resolve(dir_path) if dir_path else self._root
        if not full_path.exists() or not full_path.is_dir():
            return []
        return sorted([p.name for p in full_path.iterdir()])


# ---------------------------------------------------------------------------
# Content-addressed path builders
# ---------------------------------------------------------------------------

def build_asset_path(
    design_id: str,
    device_id: str,
    case_type: str,
    view: str,
    width: int,
    hash_prefix: str,
    *,
    format: str = "webp",
) -> str:
    """Build a content-addressed asset path.

    Format: ``assets/<design_id>/<device_id>/<case_type>/<view>-w<width>.<hash12>.webp``

    Parameters
    ----------
    design_id : str
        Design ID (component ID format).
    device_id : str
        Device ID (component ID format).
    case_type : str
        Case type token.
    view : str
        View token.
    width : int
        Image width in pixels.
    hash_prefix : str
        12-character content hash prefix.
    format : str
        File format extension (default "webp").

    Returns
    -------
    str
        Relative asset path.
    """
    return (
        f"assets/{design_id}/{device_id}/{case_type}/"
        f"{view}-w{width}.{hash_prefix}.{format}"
    )


def build_asset_dir(
    design_id: str,
    device_id: str,
    case_type: str,
) -> str:
    """Build the directory path for a variant's assets.

    Format: ``assets/<design_id>/<device_id>/<case_type>/``
    """
    return f"assets/{design_id}/{device_id}/{case_type}/"
