---
trigger: always_on
---
# 06 — Code Quality & Production Docstring Standards

Quy chuẩn bắt buộc cho MỌI Agent và Subagent khi viết mới, bảo trì hoặc refactor mã nguồn trong hệ thống News-Scape theo chuẩn **Google Python Style Guide** và phong cách **Production Deliverable**.

---

## 1. Triết Lý Trình Bày (Production Deliverable Standard)

Mã nguồn bàn giao cho doanh nghiệp phải đạt tính trực diện, chính xác và chuyên nghiệp:
- **Mục đích**: Định nghĩa chính xác hàm/lớp/module nhận gì, xử lý gì và trả về gì.
- **Văn phong**: Dùng câu khẳng định, mệnh lệnh trực diện (imperative mood), khách quan và súc tích.
- **Chủ ngữ**: Không ngôi (khuyết chủ ngữ, bắt đầu bằng động từ hành động như "Tính toán...", "Phân loại...", "Xây dựng..."). Tuyệt đối không dùng ngôi thứ nhất ("chúng ta", "tôi", "hãy cùng").
- **Comments**: Chỉ giải thích logic nghiệp vụ hoặc thuật toán không hiển nhiên. Tuyệt đối không ghi nhật ký gỡ lỗi, lịch sử thay đổi hay giải trình cá nhân trong code.

---

## 2. Danh Mục Từ Cấm & Sáo Ngữ (Strict Blacklist)

Tuyệt đối KHÔNG sử dụng các cụm từ và mẫu ký tự sau trong docstrings, comments và tài liệu kỹ thuật:

1. **Từ nối dông dài / Khái quát hóa thừa**:
   - `nhìn chung`, `thông thường`, `nói chung`, `về cơ bản`
2. **Sáo ngữ & Cảm thán**:
   - `đáng chú ý`, `cần lưu ý rằng`, `đóng vai trò quan trọng`
   - `toàn diện`, `mạnh mẽ`, `hiệu quả cao`, `tối ưu nhất`
3. **Giọng văn giảng giải / Sư phạm / Ngôi thứ nhất**:
   - `chúng ta`, `chúng ta hãy`, `tôi`, `bạn có thể thấy rằng`
4. **Câu hỏi tu từ**:
   - Bất kỳ câu văn nào kết thúc bằng dấu chấm hỏi `?` trong docstrings kỹ thuật.
5. **Emoji & Ký tự trang trí**:
   - Loại bỏ 100% emoji (⚠️, ⨝, 🚀, 💡,...) trong docstrings và comments kỹ thuật.
6. **Thẻ tạm / Vết định danh phiên bản nháp**:
   - `[LEGACY / COLD BACKUP...]`, `TODO tạm thời`, `ĐÓNG BĂNG`, `L1_VERSION`.

---

## 3. Cấu Trúc Docstring Chuẩn (Google Style)

### A. Module Docstring (Đầu tệp)
- Tóm tắt vai trò của module bằng **1 câu khẳng định duy nhất**.
- Nếu có cấu hình/hằng số quan trọng, liệt kê bằng gạch đầu dòng ngắn gọn.
```python
"""Quản lý tiến trình phân phối và đóng gói tác vụ phân tích tin tức."""
```

### B. Class Docstring (Lớp đối tượng)
- Dòng đầu tiên tóm tắt vai trò của lớp.
- Theo sau là section `Attributes:` (nếu có thuộc tính công khai).
```python
class AgentRunner:
    """Điều phối vòng đời xuất tác vụ cho subagent và tiếp nhận kết quả.

    Attributes:
        store: Phiên kết nối kho dữ liệu SQLite.
        task_dir: Thư mục chứa gói công việc đầu ra.
    """
```

### C. Function / Method Docstring (Hàm & Phương thức)
- **Dòng 1**: Câu mệnh lệnh khẳng định kết thúc bằng dấu chấm (VD: "Tính toán...", "Xuất danh sách...").
- **Args**: Tên tham số kèm kiểu và mô tả ý nghĩa logic.
- **Returns**: Kiểu dữ liệu và mô tả giá trị trả về.
- **Raises**: Các ngoại lệ có thể phát sinh (nếu có).
```python
def export_tasks(self, limit: int = 20, *, require_l1: bool = True) -> list[dict]:
    """Tiếp nhận các công việc đang chờ và xuất thành gói công việc JSON.

    Args:
        limit: Số lượng tác vụ tối đa cần xuất.
        require_l1: Chỉ nhận bài viết đã qua kiểm định L1 đạt chuẩn.

    Returns:
        Danh sách từ điển thông tin các tác vụ đã xuất thành công.

    Raises:
        RuntimeError: Khi thư mục xuất tác vụ không thể ghi dữ liệu.
    """
```

---

## 4. Quy Chuẩn Viết Code & Kiểm Định Nghiêm Ngặt

1. **Bảo toàn Chữ ký & Logic**:
   - Không tự ý đổi tên hàm, thứ tự tham số, kiểu dữ liệu trả về đã được thỏa thuận trong Data Contract.
   - Không được làm ảnh hưởng đến các câu lệnh SQL, transaction và schema cơ sở dữ liệu (`monocle.db`).
2. **Kiểm định Cú pháp AST**:
   - Mọi tệp Python sau khi chỉnh sửa BẮT BUỘC phải biên dịch thành công qua `ast.parse()`, không có ngoại lệ cú pháp.
3. **Bảo toàn Bộ Kiểm Thử (Pytest Integrity)**:
   - Trước khi kết thúc phiên làm việc, BẮT BUỘC chạy `pytest` để kiểm chứng 100% unit tests vẫn PASS.
