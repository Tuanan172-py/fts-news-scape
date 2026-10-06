"""Xuất bản một chiều dữ liệu của một ngày đã đóng sang thư mục SharePoint (ADR 0020).

Đích xuất bản là biến môi trường `NEWS_SCAPE_PUBLISH_DIR`. Không đặt thì publisher tắt
(mức L0) và không ghi gì. Mọi tệp được dựng ở `paths.publish_staging_dir()` rồi mới chép
sang đích theo giao thức `.<tên>.partial` → fsync → `os.replace`, không ghi đè tệp đã có.

Bố cục dưới đích:

- `review/monocle_review_<YYYYMMDD>.db`: bản `VACUUM INTO` của DB vận hành.
- `parquet/<bảng>/year=YYYY/month=MM/part-<YYYYMMDD>.parquet`: `articles`, `analysis`, `mentions`.
- `bronze/YYYY/MM/DD/<nguồn>.tar.xz`: HTML thô và `.meta.json` của ngày.
- `users/output/<user>/<YYYY-MM-DD>.xlsx`: tệp giao hàng của ngày.
- `_manifest/<YYYYMMDD>.json` (bản sửa sau là `<YYYYMMDD>.r<n>.json`) và `_manifest/latest.json`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import tarfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.agent.article_contract import not_code_first_sql
from src.core import paths

PUBLISH_DIR_ENV = "NEWS_SCAPE_PUBLISH_DIR"
MANIFEST_SCHEMA = "news-scape-publish-manifest/1"
DEFAULT_KEEP_REVIEW_DAYS = 7
DEPRECATED_COLUMNS = frozenset({"materiality", "event_type", "impact_area"})
HEAVY_COLUMNS = frozenset({"content_html"})

# Bảng Parquet → (bảng DB, cột ngày). `articles` chọn theo ngày thu thập (`fetched_at`);
# `analysis` và `mentions` chọn theo ngày nạp qua cổng DoD (`created_at`). Cả ba cột đều
# là chuỗi ISO giờ Việt Nam, nên 10 ký tự đầu là ngày lịch địa phương.
PARQUET_TABLES: dict[str, tuple[str, str]] = {
    "articles": ("articles", "fetched_at"),
    "analysis": ("agent_outputs", "created_at"),
    "mentions": ("l1_outputs", "created_at"),
}

# Điều kiện lọc dòng thêm theo bảng DB. Bản code-first không phải kết quả phân tích nên
# không vào bảng `mentions` (ADR 0010 D4).
ROW_FILTERS: dict[str, str] = {"l1_outputs": not_code_first_sql()}

_MANIFEST_RE = re.compile(r"^(\d{8})(?:\.r(\d+))?\.json$")
_CHUNK = 1 << 20


class PublishConflictError(RuntimeError):
    """Báo tệp đích đã tồn tại với nội dung khác bản dựng."""


@dataclass
class FileOutcome:
    """Kết quả xuất bản một tệp.

    Attributes:
        path: Đường dẫn tương đối dưới đích, dấu gạch chéo xuôi.
        kind: Loại tệp: review, parquet, bronze, users.
        action: planned, copied, skipped, conflict hoặc error.
        size: Kích thước byte; None khi chưa dựng.
        sha256: Mã băm SHA256; None khi chưa dựng.
        rows: Số dòng với tệp dạng bảng.
        message: Mô tả lỗi khi có.
        members: Thành viên của gói Bronze kèm SHA256 tệp gốc.
    """

    path: str
    kind: str
    action: str = "planned"
    size: int | None = None
    sha256: str | None = None
    rows: int | None = None
    message: str = ""
    members: list[dict[str, Any]] | None = None


@dataclass
class PublishResult:
    """Kết quả một lần xuất bản.

    Attributes:
        status: ok, partial, failed hoặc disabled.
        day: Ngày xuất bản, dạng YYYY-MM-DD.
        message: Mô tả ngắn cho nhật ký và cảnh báo.
        target: Thư mục đích; None khi tắt.
        manifest: Đường dẫn tương đối của manifest ngày đã ghi.
        files: Kết quả từng tệp.
        pruned: Bản review cũ đã xoá.
    """

    status: str
    day: str
    message: str
    target: str | None = None
    manifest: str | None = None
    files: list[FileOutcome] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Chuyển kết quả sang từ điển để ghi nhật ký.

        Returns:
            Từ điển các trường, không kèm danh sách thành viên Bronze.
        """
        out = asdict(self)
        for f in out["files"]:
            f.pop("members", None)
        return out


def publish_target(override: str | Path | None = None) -> Path | None:
    """Phân giải thư mục đích xuất bản.

    Args:
        override: Đích dùng thay biến môi trường cho lần chạy này.

    Returns:
        Đường dẫn tuyệt đối của đích, hoặc None khi publisher tắt.
    """
    raw = str(override) if override else os.environ.get(PUBLISH_DIR_ENV, "").strip()
    return Path(raw).expanduser().absolute() if raw else None


def sha256_file(path: Path) -> str:
    """Tính SHA256 của một tệp.

    Args:
        path: Tệp cần băm.

    Returns:
        Chuỗi hex 64 ký tự.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_no_overwrite(src: Path, dst: Path, sha: str | None = None) -> str:
    """Chép một tệp sang đích theo giao thức partial → fsync → replace, không ghi đè.

    Args:
        src: Tệp đã dựng xong ở staging.
        dst: Đường dẫn cuối cùng dưới đích.
        sha: SHA256 của `src` nếu đã tính.

    Returns:
        `copied` khi vừa chép, `skipped` khi đích đã có tệp cùng SHA256.

    Raises:
        PublishConflictError: Khi đích đã có tệp cùng tên nhưng khác SHA256.
    """
    sha = sha or sha256_file(src)
    if dst.exists():
        if sha256_file(dst) == sha:
            return "skipped"
        raise PublishConflictError(f"{dst.name} đã có ở đích với SHA256 khác, không ghi đè.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(f".{dst.name}.partial")
    with open(src, "rb") as fin, open(part, "wb") as fout:
        shutil.copyfileobj(fin, fout, _CHUNK)
        fout.flush()
        os.fsync(fout.fileno())
    if dst.exists():
        part.unlink(missing_ok=True)
        raise PublishConflictError(f"{dst.name} xuất hiện ở đích trong lúc chép, không ghi đè.")
    os.replace(part, dst)
    return "copied"


def _write_json_replace(path: Path, data: dict[str, Any]) -> None:
    """Ghi JSON bằng tệp tạm rồi `os.replace`, dành cho `latest.json`.

    Args:
        path: Tệp đích.
        data: Nội dung.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f".{path.name}.partial")
    with open(part, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(part, path)


def _now_iso() -> str:
    """Trả về thời điểm hiện tại giờ Việt Nam dạng ISO.

    Returns:
        Chuỗi ISO 8601 có múi giờ.
    """
    from src.core.models import now_vn_iso

    return now_vn_iso()


def _ymd(day: date) -> str:
    """Định dạng ngày thành YYYYMMDD.

    Args:
        day: Ngày cần định dạng.

    Returns:
        Chuỗi YYYYMMDD.
    """
    return day.strftime("%Y%m%d")


# ── Đọc manifest đã có ở đích ────────────────────────────────────────────────

def _day_manifests(target: Path) -> dict[str, tuple[int, Path]]:
    """Liệt kê bản manifest mới nhất của từng ngày dưới đích.

    Args:
        target: Thư mục đích.

    Returns:
        Từ điển YYYYMMDD → (số bản sửa, đường dẫn).
    """
    out: dict[str, tuple[int, Path]] = {}
    mdir = target / "_manifest"
    if not mdir.is_dir():
        return out
    for p in mdir.iterdir():
        m = _MANIFEST_RE.match(p.name)
        if not m:
            continue
        rev = int(m.group(2) or 1)
        if m.group(1) not in out or rev > out[m.group(1)][0]:
            out[m.group(1)] = (rev, p)
    return out


def _load_json(path: Path) -> dict[str, Any] | None:
    """Đọc một tệp JSON, trả None khi thiếu hoặc hỏng.

    Args:
        path: Tệp JSON.

    Returns:
        Nội dung hoặc None.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _manifest_complete(target: Path, manifest: dict[str, Any]) -> bool:
    """Kiểm mọi tệp trong manifest còn ở đích với đúng kích thước.

    Bản review có thể đã bị xoá theo chính sách giữ N bản, nên không tính vào điều kiện đủ.

    Args:
        target: Thư mục đích.
        manifest: Manifest ngày.

    Returns:
        True khi đủ tệp.
    """
    for f in manifest.get("files", []):
        if f.get("kind") == "review":
            continue
        p = target / f["path"]
        if not p.is_file() or p.stat().st_size != f.get("size"):
            return False
    return True


# ── Dựng tệp ở staging ───────────────────────────────────────────────────────

def _plan(day: date, db: Path) -> list[FileOutcome]:
    """Lập danh sách tệp sẽ xuất bản cho một ngày, không ghi gì.

    Args:
        day: Ngày xuất bản.
        db: DB vận hành.

    Returns:
        Danh sách FileOutcome ở trạng thái planned.
    """
    ymd = _ymd(day)
    plan = [FileOutcome(f"review/monocle_review_{ymd}.db", "review")]
    for name in PARQUET_TABLES:
        plan.append(FileOutcome(
            f"parquet/{name}/year={day:%Y}/month={day:%m}/part-{ymd}.parquet", "parquet"))
    bronze = paths.bronze_dir()
    if bronze.is_dir():
        for src_dir in sorted(bronze.iterdir()):
            if (src_dir / ymd).is_dir() and any((src_dir / ymd).iterdir()):
                plan.append(FileOutcome(
                    f"bronze/{day:%Y}/{day:%m}/{day:%d}/{src_dir.name}.tar.xz", "bronze"))
    users = paths.users_output_dir()
    if users.is_dir():
        for udir in sorted(users.iterdir()):
            if udir.is_dir() and not udir.name.startswith("_") \
                    and (udir / f"{day.isoformat()}.xlsx").is_file():
                plan.append(FileOutcome(f"users/output/{udir.name}/{day.isoformat()}.xlsx", "users"))
    return plan


def _build_review(db: Path, out: Path) -> None:
    """Dựng bản review bằng `VACUUM INTO` qua kết nối chỉ đọc.

    Args:
        db: DB vận hành.
        out: Tệp đích ở staging.
    """
    from src.db.snapshot import create_db_snapshot

    final = create_db_snapshot(db, out, overwrite=True)
    if final != out.resolve():
        os.replace(final, out)


def _build_parquet(db: Path, table: str, date_col: str, day: date, out: Path) -> int:
    """Xuất các dòng của một ngày từ một bảng DB sang Parquet.

    Bỏ cột nội dung nặng (đã có HTML thô ở Bronze) và cột đã ngừng dùng.

    Args:
        db: DB vận hành.
        table: Bảng nguồn.
        date_col: Cột ngày dùng để chọn dòng.
        day: Ngày xuất bản.
        out: Tệp đích ở staging.

    Returns:
        Số dòng đã ghi.
    """
    import pandas as pd

    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        keep = [c for c in cols if c not in HEAVY_COLUMNS and c not in DEPRECATED_COLUMNS]
        if not keep:
            raise RuntimeError(f"Bảng {table} không có trong DB.")
        extra = f" AND {ROW_FILTERS[table]}" if table in ROW_FILTERS else ""
        sql = (f"SELECT {', '.join(keep)} FROM {table} "
               f"WHERE substr({date_col}, 1, 10) = ?{extra} ORDER BY rowid")
        frame = pd.read_sql_query(sql, conn, params=(day.isoformat(),))
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, engine="pyarrow", index=False)
    return len(frame)


def _build_bronze(src_dir: Path, out: Path) -> list[dict[str, Any]]:
    """Nén thư mục Bronze của một nguồn trong một ngày thành `.tar.xz`.

    Thành viên sắp theo tên, chủ sở hữu đặt về 0, nên cùng đầu vào cho cùng gói.

    Args:
        src_dir: Thư mục `<bronze>/<nguồn>/<YYYYMMDD>`.
        out: Tệp đích ở staging.

    Returns:
        Danh sách thành viên: tên trong gói, kích thước, SHA256 tệp gốc.
    """
    base = src_dir.parent.parent
    members = []
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:xz") as tar:
        for f in sorted(p for p in src_dir.rglob("*") if p.is_file()):
            arc = f.relative_to(base).as_posix()
            info = tar.gettarinfo(str(f), arcname=arc)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(f, "rb") as fh:
                tar.addfile(info, fh)
            members.append({"name": arc, "size": info.size, "sha256": sha256_file(f)})
    return members


def _build(item: FileOutcome, day: date, db: Path, stage: Path) -> None:
    """Dựng một tệp ở staging và điền kích thước, SHA256, số dòng.

    Tệp đã có ở staging từ lần chạy dở trước được dùng lại, giữ SHA256 ổn định.

    Args:
        item: Tệp cần dựng.
        day: Ngày xuất bản.
        db: DB vận hành.
        stage: Thư mục staging của ngày.
    """
    out = stage / item.path
    side = out.with_name(out.name + ".info.json")
    if out.is_file() and side.is_file():
        info = _load_json(side) or {}
        item.rows, item.members = info.get("rows"), info.get("members")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        if item.kind == "review":
            _build_review(db, out)
        elif item.kind == "parquet":
            name = item.path.split("/")[1]
            table, col = PARQUET_TABLES[name]
            item.rows = _build_parquet(db, table, col, day, out)
        elif item.kind == "bronze":
            source = Path(item.path).name[: -len(".tar.xz")]
            item.members = _build_bronze(paths.bronze_dir() / source / _ymd(day), out)
        elif item.kind == "users":
            _, _, user, fname = item.path.split("/")
            shutil.copyfile(paths.users_output_dir() / user / fname, out)
        side.write_text(json.dumps({"rows": item.rows, "members": item.members},
                                   ensure_ascii=False), encoding="utf-8")
    item.size = out.stat().st_size
    item.sha256 = sha256_file(out)


# ── Manifest và chính sách giữ bản review ────────────────────────────────────

def _manifest_entry(item: FileOutcome) -> dict[str, Any]:
    """Dựng mục manifest của một tệp.

    Args:
        item: Tệp đã xuất bản.

    Returns:
        Từ điển mục manifest.
    """
    e: dict[str, Any] = {"path": item.path, "kind": item.kind, "size": item.size,
                         "sha256": item.sha256}
    if item.rows is not None:
        e["rows"] = item.rows
    if item.members is not None:
        e["members"] = item.members
    return e


def _prune_reviews(target: Path, keep: int) -> list[str]:
    """Xoá bản review cũ hơn N ngày gần nhất, chỉ những bản do publisher ghi.

    Một bản review chỉ bị xoá khi manifest của ngày đó liệt kê nó và SHA256 khớp.

    Args:
        target: Thư mục đích.
        keep: Số ngày review giữ lại.

    Returns:
        Đường dẫn tương đối của các bản đã xoá.
    """
    reviews = []
    for ymd, (_, mpath) in _day_manifests(target).items():
        for f in (_load_json(mpath) or {}).get("files", []):
            if f.get("kind") == "review":
                reviews.append((ymd, f))
    reviews.sort(key=lambda t: t[0], reverse=True)
    pruned = []
    for _, f in reviews[max(keep, 1):]:
        p = target / f["path"]
        if p.is_file() and sha256_file(p) == f.get("sha256"):
            p.unlink()
            pruned.append(f["path"])
    return pruned


def _write_day_manifest(target: Path, day: date, files: list[FileOutcome],
                        existing: tuple[int, Path] | None) -> str:
    """Ghi manifest ngày; nội dung đổi so với bản trước thì ghi bản sửa mới.

    Args:
        target: Thư mục đích.
        day: Ngày xuất bản.
        files: Các tệp đã có ở đích.
        existing: Bản manifest mới nhất của ngày nếu có.

    Returns:
        Đường dẫn tương đối của manifest có hiệu lực.
    """
    entries = sorted((_manifest_entry(f) for f in files), key=lambda e: e["path"])
    if existing:
        old = _load_json(existing[1]) or {}
        old_set = {(e["path"], e.get("sha256")) for e in old.get("files", [])}
        if old_set == {(e["path"], e["sha256"]) for e in entries}:
            return f"_manifest/{existing[1].name}"
    rev = existing[0] + 1 if existing else 1
    name = f"{_ymd(day)}.json" if rev == 1 else f"{_ymd(day)}.r{rev}.json"
    data = {"schema": MANIFEST_SCHEMA, "day": day.isoformat(), "revision": rev,
            "generated_at": _now_iso(), "host": socket.gethostname(), "files": entries}
    stage = paths.publish_staging_dir() / "_manifest"
    stage.mkdir(parents=True, exist_ok=True)
    tmp = stage / name
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    copy_no_overwrite(tmp, target / "_manifest" / name)
    tmp.unlink(missing_ok=True)
    return f"_manifest/{name}"


def _write_latest(target: Path, day: date, manifest_rel: str, pruned: list[str]) -> None:
    """Ghi `_manifest/latest.json` sau cùng, trỏ tới ngày mới nhất đã xuất bản.

    Args:
        target: Thư mục đích.
        day: Ngày vừa xuất bản.
        manifest_rel: Manifest có hiệu lực của ngày vừa xuất bản.
        pruned: Bản review vừa xoá.
    """
    days = _day_manifests(target)
    newest = max(days)
    latest_rel = f"_manifest/{days[newest][1].name}"
    data = {"schema": MANIFEST_SCHEMA, "updated_at": _now_iso(), "host": socket.gethostname(),
            "day": f"{newest[:4]}-{newest[4:6]}-{newest[6:]}", "manifest": latest_rel,
            "manifests": sorted(f"_manifest/{p.name}" for _, p in days.values()),
            "last_published": {"day": day.isoformat(), "manifest": manifest_rel},
            "pruned": pruned}
    _write_json_replace(target / "_manifest" / "latest.json", data)


# ── Điểm vào ─────────────────────────────────────────────────────────────────

def publish_day(day: date, *, dry_run: bool = False, force: bool = False,
                target: str | Path | None = None, db_path: str | Path | None = None,
                keep_review_days: int | None = None) -> PublishResult:
    """Xuất bản dữ liệu của một ngày đã đóng sang thư mục đích.

    Manifest ngày đã có và đủ tệp thì không làm lại, trừ khi `force`. Lần chạy dở trước
    được làm tiếp nhờ tệp còn ở staging và tệp đã có ở đích cùng SHA256. Mọi lỗi được bắt
    lại và trả về trong kết quả, không ném ra ngoài.

    Args:
        day: Ngày xuất bản.
        dry_run: True thì chỉ lập kế hoạch tệp, không ghi gì.
        force: True thì kiểm và chép lại phần thiếu dù manifest ngày đã đủ.
        target: Đích dùng thay `NEWS_SCAPE_PUBLISH_DIR` cho lần chạy này.
        db_path: DB vận hành; mặc định theo `resolve_db_path()`.
        keep_review_days: Số bản review giữ lại; mặc định theo `publish.keep_review_days`.

    Returns:
        PublishResult với trạng thái ok, partial, failed hoặc disabled.
    """
    tgt = publish_target(target)
    if tgt is None:
        return PublishResult("disabled", day.isoformat(),
                             f"Chưa đặt {PUBLISH_DIR_ENV}: publisher tắt (mức L0).")
    try:
        return _publish(day, tgt, dry_run=dry_run, force=force, db_path=db_path,
                        keep_review_days=keep_review_days)
    except Exception as exc:  # noqa: BLE001
        return PublishResult("failed", day.isoformat(), f"Xuất bản lỗi: {exc}", target=str(tgt))


def _publish(day: date, tgt: Path, *, dry_run: bool, force: bool,
             db_path: str | Path | None, keep_review_days: int | None) -> PublishResult:
    """Thực hiện xuất bản; lỗi được `publish_day` bắt lại.

    Args:
        day: Ngày xuất bản.
        tgt: Thư mục đích.
        dry_run: Chỉ lập kế hoạch.
        force: Bỏ qua điều kiện manifest đã đủ.
        db_path: DB vận hành.
        keep_review_days: Số bản review giữ lại.

    Returns:
        PublishResult.
    """
    if db_path is None:
        from src.core.config import resolve_db_path
        db_path = resolve_db_path()
    db = Path(db_path)
    if keep_review_days is None:
        from src.ops.config import load_config
        keep_review_days = int((load_config().get("publish") or {}).get(
            "keep_review_days", DEFAULT_KEEP_REVIEW_DAYS))
    iso_day = day.isoformat()
    existing = _day_manifests(tgt).get(_ymd(day)) if tgt.is_dir() else None
    old = (_load_json(existing[1]) or {}) if existing else {}
    if existing and not force and _manifest_complete(tgt, old):
        return PublishResult("ok", iso_day, f"Ngày {iso_day} đã xuất bản, không làm lại.",
                             target=str(tgt), manifest=f"_manifest/{existing[1].name}")
    plan = _plan(day, db)
    if dry_run:
        return PublishResult("ok", iso_day, f"Kế hoạch {len(plan)} tệp, chưa ghi gì.",
                             target=str(tgt), files=plan)
    if not db.is_file():
        return PublishResult("failed", iso_day, f"Không thấy DB vận hành {db}.", target=str(tgt))

    vouched = {f["path"]: f for f in old.get("files", [])}
    stage = paths.publish_staging_dir() / _ymd(day)
    done: list[FileOutcome] = []
    for item in plan:
        dst = tgt / item.path
        prior = vouched.get(item.path)
        try:
            if prior and dst.is_file() and sha256_file(dst) == prior.get("sha256"):
                # Tệp manifest đã xác nhận: giữ nguyên, không dựng lại (bản review đổi mỗi lần).
                item.size, item.sha256 = prior.get("size"), prior.get("sha256")
                item.rows, item.members = prior.get("rows"), prior.get("members")
                item.action = "skipped"
            else:
                _build(item, day, db, stage)
                item.action = copy_no_overwrite(stage / item.path, dst, item.sha256)
            done.append(item)
        except PublishConflictError as exc:
            item.action, item.message = "conflict", str(exc)
        except Exception as exc:  # noqa: BLE001
            item.action, item.message = "error", f"{type(exc).__name__}: {exc}"

    bad = [f for f in plan if f.action in ("conflict", "error")]
    if bad:
        status = "partial" if done else "failed"
        detail = "; ".join(f"{f.path}: {f.message}" for f in bad[:3])
        return PublishResult(status, iso_day, f"{len(bad)}/{len(plan)} tệp lỗi: {detail}",
                             target=str(tgt), files=plan)

    manifest_rel = _write_day_manifest(tgt, day, done, existing)
    pruned = _prune_reviews(tgt, keep_review_days)
    _write_latest(tgt, day, manifest_rel, pruned)
    shutil.rmtree(stage, ignore_errors=True)
    copied = sum(1 for f in plan if f.action == "copied")
    return PublishResult("ok", iso_day, f"Xuất bản {iso_day}: chép {copied}, giữ nguyên "
                         f"{len(plan) - copied} tệp.", target=str(tgt), manifest=manifest_rel,
                         files=plan, pruned=pruned)


def parse_day(text: str, today: date | None = None) -> date:
    """Đọc tham số ngày `YYYY-MM-DD`, `today` hoặc `yesterday`.

    Args:
        text: Chuỗi ngày.
        today: Ngày hôm nay theo giờ Việt Nam; None thì tự lấy.

    Returns:
        Ngày tương ứng.

    Raises:
        ValueError: Khi chuỗi không đúng định dạng.
    """
    from datetime import timedelta

    from src.core.models import VN_TZ

    base = today or datetime.now(VN_TZ).date()
    if text == "today":
        return base
    if text == "yesterday":
        return base - timedelta(days=1)
    return date.fromisoformat(text)
