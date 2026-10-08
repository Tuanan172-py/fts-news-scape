"""Tầng trừu tượng hóa giao diện lưu trữ cho kiến trúc Lakehouse Data Plane."""

from __future__ import annotations

import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Callable, Optional


class BaseStorageAdapter(ABC):
    """Lớp cơ sở trừu tượng cho các hệ thống lưu trữ tệp tin."""

    @abstractmethod
    def list_files(self, pattern: str) -> list[str]:
        """Liệt kê danh sách đường dẫn tệp tin khớp với mẫu tìm kiếm.

        Args:
            pattern: Chuỗi mẫu khớp đường dẫn (vd: 'dropzone/*/*/*/*.parquet').

        Returns:
            Danh sách đường dẫn tương đối của các tệp tin tìm thấy.
        """

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Đọc toàn bộ nội dung tệp tin dưới dạng chuỗi byte.

        Args:
            path: Đường dẫn tương đối của tệp tin cần đọc.

        Returns:
            Dữ liệu byte nguyên bản của tệp tin.

        Raises:
            FileNotFoundError: Khi tệp tin không tồn tại trong kho lưu trữ.
        """

    @abstractmethod
    def write_atomic(self, path: str, data: bytes) -> str:
        """Ghi dữ liệu nguyên tử vào kho lưu trữ bằng cơ chế staging an toàn.

        Args:
            path: Đường dẫn tương đối của tệp tin đích cần ghi.
            data: Dữ liệu byte cần ghi xuống kho lưu trữ.

        Returns:
            Đường dẫn tương đối của tệp tin thực tế đã được lưu.

        Raises:
            IOError: Khi thao tác ghi tệp tin thất bại.
        """

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Kiểm tra sự tồn tại của tệp tin hoặc thư mục trong kho lưu trữ.

        Args:
            path: Đường dẫn tương đối cần kiểm tra.

        Returns:
            True nếu tệp tin hoặc thư mục tồn tại, ngược lại False.
        """

    def delete(self, path: str) -> bool:
        """Xóa tệp tin khỏi kho lưu trữ.

        Args:
            path: Đường dẫn tương đối của tệp tin cần xóa.

        Returns:
            True nếu tệp tin đã được xóa thành công, ngược lại False.
        """
        raise NotImplementedError("Phương thức delete chưa được cài đặt.")

    def get_local_path(self, path: str) -> Optional[Path]:
        """Lấy đường dẫn tệp tin trên hệ thống tập tin cục bộ nếu được hỗ trợ.

        Args:
            path: Đường dẫn tương đối cần truy xuất.

        Returns:
            Đối tượng Path nếu hỗ trợ truy cập cục bộ, ngược lại None.
        """
        return None


class LocalOneDriveStorageAdapter(BaseStorageAdapter):
    """Adapter lưu trữ thao tác trên hệ thống tệp tin cục bộ và thư mục đồng bộ OneDrive.

    Attributes:
        root_dir: Đường dẫn thư mục gốc của kho dữ liệu Lakehouse.
    """

    @staticmethod
    def _strip_extended_prefix(path: Path) -> Path:
        """Loại bỏ tiền tố extended-path trên Windows nếu có.

        Args:
            path: Đường dẫn cần chuẩn hóa.

        Returns:
            Đường dẫn Path đã loại bỏ tiền tố mở rộng.
        """
        s = str(path)
        if s.startswith(("\\\\?\\", "//?/")):
            return Path(s[4:])
        return path

    def _to_rel_posix(self, path: Path) -> str:
        """Chuyển đổi đường dẫn tuyệt đối sang đường dẫn tương đối chuẩn POSIX.

        Args:
            path: Đường dẫn tuyệt đối cần tính tương đối.

        Returns:
            Chuỗi đường dẫn tương đối dạng chuẩn POSIX.
        """
        norm_target = self._strip_extended_prefix(path)
        norm_root = self._strip_extended_prefix(self.root_dir)
        return norm_target.relative_to(norm_root).as_posix()

    def __init__(self, root_dir: str | Path) -> None:
        """Khởi tạo adapter lưu trữ cục bộ.

        Args:
            root_dir: Thư mục gốc dùng làm kho lưu trữ dữ liệu.
        """
        resolved = Path(root_dir).resolve()
        self.root_dir = self._strip_extended_prefix(resolved)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel_path: str) -> Path:
        """Chuyển đổi đường dẫn tương đối thành đường dẫn tuyệt đối an toàn.

        Args:
            rel_path: Đường dẫn tương đối cần xử lý.

        Returns:
            Đường dẫn tuyệt đối bên trong thư mục gốc.
        """
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        return self._strip_extended_prefix((self.root_dir / clean_rel).resolve())

    def list_files(self, pattern: str) -> list[str]:
        """Liệt kê danh sách đường dẫn tệp tin khớp với mẫu tìm kiếm.

        Args:
            pattern: Chuỗi mẫu khớp đường dẫn dạng glob.

        Returns:
            Danh sách đường dẫn tương đối dạng chuẩn POSIX của các tệp tin.
        """
        clean_pat = pattern.replace("\\", "/").lstrip("/")
        results: list[str] = []
        for p in self.root_dir.glob(clean_pat):
            if p.is_file():
                # Bỏ qua các tệp tạm thời và tệp dở dang
                if p.name.endswith((".partial", ".tmp")):
                    continue
                results.append(self._to_rel_posix(p))
        results.sort()
        return results

    def read_bytes(self, path: str) -> bytes:
        """Đọc toàn bộ nội dung tệp tin dưới dạng chuỗi byte qua stream an toàn.

        Args:
            path: Đường dẫn tương đối của tệp tin cần đọc.

        Returns:
            Dữ liệu byte nguyên bản của tệp tin.

        Raises:
            FileNotFoundError: Khi tệp tin không tồn tại.
        """
        target = self._resolve(path)
        if not target.exists():
            raise FileNotFoundError(f"Tệp tin không tồn tại: {path}")
        with open(target, "rb") as f:
            return f.read()

    def write_atomic(self, path: str, data: bytes) -> str:
        """Ghi dữ liệu nguyên tử ra đĩa qua quy trình staging, fsync và os.replace.

        Args:
            path: Đường dẫn tương đối của tệp tin đích.
            data: Dữ liệu byte cần ghi xuống đĩa.

        Returns:
            Đường dẫn tương đối của tệp tin đã ghi thành công.

        Raises:
            PermissionError: Khi tệp tin bị khóa độc quyền và không thể thay thế.
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Kiểm tra nội dung byte nếu file đích đã tồn tại để tránh kích hoạt sync thừa
        if target.exists():
            try:
                if target.stat().st_size == len(data):
                    existing_hash = hashlib.sha256(target.read_bytes()).digest()
                    new_hash = hashlib.sha256(data).digest()
                    if existing_hash == new_hash:
                        return self._to_rel_posix(target)
            except Exception:
                pass

        # Bước 1: Ghi ra tệp tạm duy nhất .partial trong cùng thư mục
        unique_token = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        tmp_path = target.parent / f"{target.stem}_{unique_token}{target.suffix}.partial"

        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
                f.flush()
                # Bước 2: Bảo đảm dữ liệu được xả hoàn toàn xuống đĩa cứng
                os.fsync(f.fileno())

            # Bước 3: Thay thế nguyên tử vào tệp đích
            os.replace(tmp_path, target)
            return self._to_rel_posix(target)
        except PermissionError:
            # Fallback lưu bản ghi snapshot nếu tệp đích bị khóa độc quyền bởi tiến trình khác
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
        """Kiểm tra sự tồn tại của tệp tin hoặc thư mục.

        Args:
            path: Đường dẫn tương đối cần kiểm tra.

        Returns:
            True nếu đường dẫn tồn tại trên đĩa, ngược lại False.
        """
        return self._resolve(path).exists()

    def delete(self, path: str) -> bool:
        """Xóa tệp tin khỏi thư mục gốc.

        Args:
            path: Đường dẫn tương đối của tệp tin cần xóa.

        Returns:
            True nếu tệp tin được xóa thành công, ngược lại False.
        """
        target = self._resolve(path)
        if target.is_file():
            target.unlink()
            return True
        return False

    def get_local_path(self, path: str) -> Optional[Path]:
        """Lấy đường dẫn tuyệt đối trên hệ thống tập tin cục bộ.

        Args:
            path: Đường dẫn tương đối trong kho dữ liệu.

        Returns:
            Đối tượng Path tương ứng trên máy tính.
        """
        return self._resolve(path)


class GraphApiStorageAdapter(BaseStorageAdapter):
    """Adapter lưu trữ kết nối Microsoft Graph API cho SharePoint Sandbox.

    Attributes:
        tenant_id: Mã định danh thuê bao Azure AD.
        client_id: Mã định danh ứng dụng Entra ID.
        client_secret: Khóa bí mật xác thực ứng dụng.
        drive_id: Mã định danh thư viện tài liệu SharePoint.
    """

    def __init__(
        self,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        drive_id: str = "",
    ) -> None:
        """Khởi tạo adapter kết nối Microsoft Graph API.

        Args:
            tenant_id: Mã định danh thuê bao Azure AD.
            client_id: Mã định danh ứng dụng Entra ID.
            client_secret: Khóa bí mật xác thực ứng dụng.
            drive_id: Mã định danh thư viện tài liệu SharePoint.
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.drive_id = drive_id

    def list_files(self, pattern: str) -> list[str]:
        """Liệt kê danh sách tệp tin qua Microsoft Graph API endpoint.

        Args:
            pattern: Chuỗi mẫu khớp đường dẫn tìm kiếm.

        Raises:
            NotImplementedError: Khi chưa được cấu hình thông tin định danh IT.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )

    def read_bytes(self, path: str) -> bytes:
        """Tải nội dung tệp tin từ SharePoint qua Graph API.

        Args:
            path: Đường dẫn tệp tin trên SharePoint.

        Raises:
            NotImplementedError: Khi chưa được cấu hình thông tin định danh IT.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )

    def write_atomic(self, path: str, data: bytes) -> str:
        """Tải lên tệp tin lên SharePoint qua Graph API session.

        Args:
            path: Đường dẫn tệp tin đích trên SharePoint.
            data: Dữ liệu byte cần tải lên.

        Raises:
            NotImplementedError: Khi chưa được cấu hình thông tin định danh IT.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )

    def exists(self, path: str) -> bool:
        """Kiểm tra sự tồn tại của tệp tin trên SharePoint qua Graph API.

        Args:
            path: Đường dẫn tệp tin cần kiểm tra.

        Raises:
            NotImplementedError: Khi chưa được cấu hình thông tin định danh IT.
        """
        raise NotImplementedError(
            "GraphApiStorageAdapter yêu cầu thông tin xác thực ứng dụng Azure AD từ IT."
        )
