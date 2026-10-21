"""Abstract the storage interface of the Lakehouse Data Plane architecture."""

from __future__ import annotations

import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Callable, Optional


class BaseStorageAdapter(ABC):
    """Abstract base class for file storage systems."""

    @abstractmethod
    def list_files(self, pattern: str) -> list[str]:
        """List the file paths that match a pattern.

        Args:
            pattern: Path pattern (for example 'dropzone/*/*/*/*.parquet').

        Returns:
            Relative paths of the files found.
        """

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read the whole file content as bytes.

        Args:
            path: Relative path of the file to read.

        Returns:
            Raw bytes of the file.

        Raises:
            FileNotFoundError: If the file does not exist in the store.
        """

    @abstractmethod
    def write_atomic(self, path: str, data: bytes) -> str:
        """Write data atomically to the store through safe staging.

        Args:
            path: Relative path of the target file.
            data: Bytes to write to the store.

        Returns:
            Relative path of the file actually saved.

        Raises:
            IOError: If the write fails.
        """

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check whether a file or directory exists in the store.

        Args:
            path: Relative path to check.

        Returns:
            True if the file or directory exists, otherwise False.
        """

    def delete(self, path: str) -> bool:
        """Delete a file from the store.

        Args:
            path: Relative path of the file to delete.

        Returns:
            True if the file was deleted, otherwise False.

        Raises:
            NotImplementedError: If the adapter does not implement deletion.
        """
        raise NotImplementedError("Phương thức delete chưa được cài đặt.")

    def get_local_path(self, path: str) -> Optional[Path]:
        """Return the local file system path of a file when supported.

        Args:
            path: Relative path to resolve.

        Returns:
            Path object if local access is supported, otherwise None.
        """
        return None


class LocalOneDriveStorageAdapter(BaseStorageAdapter):
    """Storage adapter for the local file system and the OneDrive sync folder.

    Attributes:
        root_dir: Root directory of the Lakehouse data store.
    """

    @staticmethod
    def _strip_extended_prefix(path: Path) -> Path:
        """Remove the Windows extended-path prefix if present.

        Args:
            path: Path to normalize.

        Returns:
            Path without the extended prefix.
        """
        s = str(path)
        if s.startswith(("\\\\?\\", "//?/")):
            return Path(s[4:])
        return path

    def _to_rel_posix(self, path: Path) -> str:
        """Convert an absolute path to a POSIX-style relative path.

        Args:
            path: Absolute path to make relative.

        Returns:
            Relative path string in POSIX form.
        """
        norm_target = self._strip_extended_prefix(path)
        norm_root = self._strip_extended_prefix(self.root_dir)
        return norm_target.relative_to(norm_root).as_posix()

    def __init__(self, root_dir: str | Path) -> None:
        """Initialize the local storage adapter.

        Args:
            root_dir: Root directory used as the data store.

        Raises:
            PermissionError: If the root directory points to the official site, which ADR-0023 forbids.
        """
        from src.export.publisher import is_official_target

        resolved = Path(root_dir).resolve()
        if is_official_target(resolved):
            raise PermissionError(
                f"Đích {resolved} thuộc site SharePoint chính thức (FRA - Data), bị cấm theo ADR-0023. "
                f"Chỉ được phép sử dụng sandbox FRA_DataIngestion."
            )
        self.root_dir = self._strip_extended_prefix(resolved)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel_path: str) -> Path:
        """Convert a relative path to a safe absolute path.

        Args:
            rel_path: Relative path to resolve.

        Returns:
            Absolute path inside the root directory.
        """
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        return self._strip_extended_prefix((self.root_dir / clean_rel).resolve())

    def list_files(self, pattern: str) -> list[str]:
        """List the file paths that match a pattern.

        Args:
            pattern: Glob-style path pattern.

        Returns:
            Relative POSIX-style paths of the files.
        """
        clean_pat = pattern.replace("\\", "/").lstrip("/")
        results: list[str] = []
        for p in self.root_dir.glob(clean_pat):
            if p.is_file():
                # Skip temporary and incomplete files.
                if p.name.endswith((".partial", ".tmp")):
                    continue
                results.append(self._to_rel_posix(p))
        results.sort()
        return results

    def read_bytes(self, path: str) -> bytes:
        """Read the whole file content as bytes through a safe stream.

        Args:
            path: Relative path of the file to read.

        Returns:
            Raw bytes of the file.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        target = self._resolve(path)
        if not target.exists():
            raise FileNotFoundError(f"Tệp tin không tồn tại: {path}")
        with open(target, "rb") as f:
            return f.read()

    def write_atomic(self, path: str, data: bytes) -> str:
        """Write data atomically to disk through staging, fsync and os.replace.

        Args:
            path: Relative path of the target file.
            data: Bytes to write to disk.

        Returns:
            Relative path of the file written.
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Compare the bytes when the target exists to avoid triggering a redundant sync.
        if target.exists():
            try:
                if target.stat().st_size == len(data):
                    existing_hash = hashlib.sha256(target.read_bytes()).digest()
                    new_hash = hashlib.sha256(data).digest()
                    if existing_hash == new_hash:
                        return self._to_rel_posix(target)
            except Exception:
                pass

        # Step 1: write to a unique .partial temp file in the same directory.
        unique_token = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        tmp_path = target.parent / f"{target.stem}_{unique_token}{target.suffix}.partial"

        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
                f.flush()
                # Step 2: flush the data fully to disk.
                os.fsync(f.fileno())

            # Step 3: replace the target atomically.
            os.replace(tmp_path, target)
            return self._to_rel_posix(target)
        except PermissionError:
            # Fallback: save a snapshot copy when another process holds an exclusive lock on the target.
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%H%M%S")
            fallback_target = target.parent / f"{target.stem}_{ts}{target.suffix}"
            os.replace(tmp_path, fallback_target)
            return self._to_rel_posix(fallback_target)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def exists(self, path: str) -> bool:
        """Check whether a file or directory exists.

        Args:
            path: Relative path to check.

        Returns:
            True if the path exists on disk, otherwise False.
        """
        return self._resolve(path).exists()

    def delete(self, path: str) -> bool:
        """Delete a file from the root directory.

        Args:
            path: Relative path of the file to delete.

        Returns:
            True if the file was deleted, otherwise False.
        """
        target = self._resolve(path)
        if target.is_file():
            target.unlink()
            return True
        return False

    def get_local_path(self, path: str) -> Optional[Path]:
        """Return the absolute path on the local file system.

        Args:
            path: Relative path in the data store.

        Returns:
            Corresponding Path on the machine.
        """
        return self._resolve(path)


class GraphApiStorageAdapter(BaseStorageAdapter):
    """Storage adapter that connects to the Microsoft Graph API for the SharePoint Sandbox.

    Attributes:
        tenant_id: Azure AD tenant identifier.
        client_id: Entra ID application identifier.
        client_secret: Application authentication secret.
        drive_id: SharePoint document library identifier.
    """

    def __init__(
        self,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        drive_id: str = "",
    ) -> None:
        """Initialize the Microsoft Graph API adapter.

        Args:
            tenant_id: Azure AD tenant identifier.
            client_id: Entra ID application identifier.
            client_secret: Application authentication secret.
            drive_id: SharePoint document library identifier.
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.drive_id = drive_id

    def list_files(self, pattern: str) -> list[str]:
        """List files through the Microsoft Graph API endpoint.

        Args:
            pattern: Path pattern to search.

        Returns:
            Relative paths of the files found.

        Raises:
            NotImplementedError: Always, until the IT credentials are configured.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )

    def read_bytes(self, path: str) -> bytes:
        """Download file content from SharePoint through the Graph API.

        Args:
            path: File path on SharePoint.

        Returns:
            Raw bytes of the file.

        Raises:
            NotImplementedError: Always, until the IT credentials are configured.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )

    def write_atomic(self, path: str, data: bytes) -> str:
        """Upload a file to SharePoint through a Graph API session.

        Args:
            path: Target file path on SharePoint.
            data: Bytes to upload.

        Returns:
            Path of the file saved.

        Raises:
            NotImplementedError: Always, until the IT credentials are configured.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )

    def exists(self, path: str) -> bool:
        """Check whether a file exists on SharePoint through the Graph API.

        Args:
            path: File path to check.

        Returns:
            True if the file exists, otherwise False.

        Raises:
            NotImplementedError: Always, until the IT credentials are configured.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )
