"""Bộ điều phối thực thi các tác vụ phân tích chuyên sâu của agent."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.agent.dod import check_dod, verify_preconditions
from src.agent.packet import build_task_packet, write_packet
from src.core.config import resolve_project_path
from src.core.models import now_vn_iso
from src.handoff.catalog import Catalog


class AgentRunner:
    """Điều phối xuất gói công việc cho agent và tiếp nhận kết quả phân tích.

    Attributes:
        store: Kho lưu trữ cơ sở dữ liệu.
        catalog: Đối tượng quản lý danh mục công việc Catalog.
        task_dir: Thư mục lưu trữ các tệp gói công việc JSON.
    """

    def __init__(self, store, *, task_dir: str = "data/agent_tasks"):
        """Khởi tạo bộ điều phối AgentRunner.

        Args:
            store: Kho lưu trữ cơ sở dữ liệu.
            task_dir: Thư mục lưu trữ tệp gói công việc. Mặc định 'data/agent_tasks'.
        """
        self.store = store
        self.catalog = Catalog(store)
        self.task_dir = task_dir

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _load_work_package(package_path: str) -> dict:
        # resolve_project_path: doc duoc ca ban tuong doi moi lan ban tuyet doi cu trong DB
        return json.loads(resolve_project_path(package_path).read_text(encoding="utf-8"))

    def _work_item_for(self, article_id: str) -> dict | None:
        """Lấy bản ghi công việc gần nhất tương ứng với mã bài viết.

        Args:
            article_id: Mã băm định danh của bài viết.

        Returns:
            Từ điển dữ liệu bản ghi công việc hoặc None nếu không tồn tại.
        """
        conn = self.store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM work_items WHERE article_id=? "
                "ORDER BY CASE status WHEN 'claimed' THEN 0 WHEN 'pending' THEN 1 "
                "ELSE 2 END, id DESC LIMIT 1", (article_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # -- export (producer → agent) --------------------------------------------
    def export_tasks(self, limit: int = 20, *, worker_id: str = "exporter",
                     order: str = "desc", require_l1: bool = True,
                     subscriber_only: bool = True,
                     user: str | list[str] | None = None,
                     date: str | None = None,
                     days: int | None = None,
                     dry_run: bool = False) -> list[dict]:
        """Tiếp nhận các công việc đang chờ và xuất thành gói công việc JSON.

        Args:
            limit: Giới hạn số lượng tác vụ xuất tối đa. Mặc định 20.
            worker_id: Định danh tiến trình tiếp nhận công việc.
            order: Thứ tự sắp xếp theo thời gian ('desc' hoặc 'asc').
            require_l1: Chỉ nhận bài viết đã qua kiểm định L1 đạt chuẩn.
            subscriber_only: Chỉ nhận bài viết liên quan danh mục người dùng theo dõi.
            user: Tên người dùng hoặc danh sách người dùng cần lọc cụ thể.
            date: Lọc theo ngày xuất bản cụ thể ('YYYY-MM-DD', 'today', 'all').
            days: Giới hạn số ngày gần nhất tính từ thời điểm hiện tại.
            dry_run: Chế độ chạy thử, chỉ đếm số lượng mà không nhận công việc.

        Returns:
            Danh sách từ điển thông tin các tác vụ đã xuất.
        """

        allowed_aids: set[str] | None = None
        if subscriber_only or user:
            try:
                from src.agent.entities import load_registry
                reg = load_registry()
                target_subs: set[str] = set()

                if user:
                    user_list = [user] if isinstance(user, str) else list(user)
                    for u in user_list:
                        u_clean = u.strip()
                        if u_clean in reg.subscriptions:
                            target_subs.update(reg.subscriptions[u_clean])
                        else:
                            logger.warning("[agent] Không tìm thấy đăng ký cho user: {}", u_clean)
                else:
                    for user_subs in reg.subscriptions.values():
                        target_subs.update(user_subs)

                conn = self.store.connect()
                try:
                    rows = conn.execute("SELECT article_id, output_json FROM l1_outputs WHERE dod_pass = 1").fetchall()
                    allowed_aids = set()
                    for r in rows:
                        out_json = r["output_json"]
                        if not out_json:
                            continue
                        try:
                            data = json.loads(out_json)
                            eids = [e["entity_id"] for e in data.get("entities", []) if e.get("entity_id")]
                            if any(eid in target_subs for eid in eids):
                                allowed_aids.add(r["article_id"])
                        except Exception:
                            pass
                finally:
                    conn.close()
                filter_label = f"User({user})" if user else "Active Subscribers"
                logger.info("[agent] {} filter: {}/{} bài L1 phù hợp",
                            filter_label, len(allowed_aids), len(rows))
            except Exception as e:
                logger.warning("[agent] Không thể nạp subscriptions, bỏ qua subscriber filter: {}", e)
                allowed_aids = None

        out: list[dict] = []
        if dry_run:
            # Chỉ đếm và thu thập danh sách không chuyển trạng thái thành 'claimed'
            conn = self.store.connect()
            try:
                order_clause = "ORDER BY enqueued_at DESC, id DESC" if order.lower() == "desc" else "ORDER BY enqueued_at ASC, id ASC"
                l1_clause = " AND EXISTS (SELECT 1 FROM l1_outputs l1 WHERE l1.article_id = work_items.article_id AND l1.dod_pass = 1)" if require_l1 else ""
                if allowed_aids is not None:
                    if not allowed_aids:
                        return []
                    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _allowed_aids (aid TEXT PRIMARY KEY)")
                    conn.execute("DELETE FROM _allowed_aids")
                    conn.executemany("INSERT OR IGNORE INTO _allowed_aids VALUES (?)", [(aid,) for aid in allowed_aids])
                    allowed_clause = " AND EXISTS (SELECT 1 FROM _allowed_aids aa WHERE aa.aid = work_items.article_id)"
                else:
                    allowed_clause = ""
                date_clause = ""
                params: list = []
                if date and date != "all":
                    from datetime import datetime
                    from src.core.models import VN_TZ
                    d_target = f"{datetime.now(VN_TZ):%Y-%m-%d}" if date == "today" else date
                    date_clause = " AND EXISTS (SELECT 1 FROM articles a WHERE a.url_title_hash = work_items.article_id AND substr(COALESCE(NULLIF(a.published_at, ''), a.fetched_at, work_items.enqueued_at), 1, 10) = ?)"
                    params.append(d_target)
                elif days and days > 0:
                    from datetime import datetime, timedelta
                    from src.core.models import VN_TZ
                    cutoff = f"{datetime.now(VN_TZ) - timedelta(days=days):%Y-%m-%d}"
                    date_clause = " AND EXISTS (SELECT 1 FROM articles a WHERE a.url_title_hash = work_items.article_id AND substr(COALESCE(NULLIF(a.published_at, ''), a.fetched_at, work_items.enqueued_at), 1, 10) >= ?)"
                    params.append(cutoff)
                params.append(limit)
                q = f"SELECT * FROM work_items WHERE status='pending'{l1_clause}{allowed_clause}{date_clause} {order_clause} LIMIT ?"
                rows = conn.execute(q, params).fetchall()
                for r in rows:
                    out.append({"article_id": r["article_id"], "work_item_id": r["id"], "dry_run": True})
                logger.info("[agent] [DRY-RUN] tìm thấy {} bài pending phù hợp", len(out))
                return out
            finally:
                conn.close()

        for _ in range(limit):
            item = self.catalog.claim(
                worker_id, order=order, require_l1=require_l1, allowed_article_ids=allowed_aids,
                date=date, days=days,
            )
            if item is None:
                break

            try:
                wp = self._load_work_package(item["package_path"])
            except (OSError, json.JSONDecodeError) as e:
                logger.error("[agent] load package fail {}: {}", item["package_path"], e)
                self.catalog.mark_failed(item["id"], f"package_unreadable: {e}")
                continue
            # Nhúng entity L1 đã bóc sẵn vào packet (rule 05 §2.5 — L1-Assisted Chaining).
            # l1-entity-output-v1 dùng key `entity_id` (KHÔNG có `code`).
            l1_entities = None
            if hasattr(self.store, "get_l1_output"):
                l1_rec = self.store.get_l1_output(item["article_id"])
                if l1_rec and l1_rec.get("output_json"):
                    try:
                        l1_out = json.loads(l1_rec["output_json"])
                        l1_entities = [e["entity_id"] for e in l1_out.get("entities", [])
                                       if e.get("in_list") and e.get("entity_id")]
                    except Exception:
                        pass
            if not l1_entities and hasattr(self.store, "get_l1_task"):
                l1_task = self.store.get_l1_task(item["article_id"])
                if l1_task and l1_task.get("code_first_json"):
                    try:
                        cf = json.loads(l1_task["code_first_json"])
                        l1_entities = cf.get("entity_ids", [])
                    except Exception:
                        pass

            packet = build_task_packet(wp, work_item_id=item["id"], l1_entities=l1_entities)
            path = write_packet(packet, base_dir=self.task_dir)
            out.append({
                "article_id": item["article_id"],
                "work_item_id": item["id"],
                "path": path,
                "title": wp.get("title", ""),
                "domain": wp.get("domain", ""),
                "enqueued_at": item.get("enqueued_at", ""),
                "input": packet.get("input", wp),
                "l1_entities": l1_entities,
            })
        logger.info("[agent] exported {} task-packets → {}", len(out), self.task_dir)
        return out

    # -- ingest (agent → producer) --------------------------------------------
    def ingest_output(self, output: dict | str) -> dict:
        """Tiếp nhận kết quả phân tích của agent, kiểm định chất lượng và cập nhật trạng thái.

        Args:
            output: Dữ liệu kết quả từ điển hoặc đường dẫn tệp JSON theo schema agent-output-v1.

        Returns:
            Từ điển báo cáo kết quả gồm trạng thái kiểm định, mã công việc và chi tiết lỗi nếu có.
        """
        if isinstance(output, str):
            output = json.loads(Path(output).read_text(encoding="utf-8"))
        article_id = output.get("article_id")
        if not article_id:
            return {"ok": False, "reason": "missing article_id"}

        item = self._work_item_for(article_id)
        if item is None:
            return {"ok": False, "article_id": article_id, "reason": "no work_item"}
        raw_sha256 = item["raw_sha256"]

        # Idempotent replay — đã có output đạt DoD thì trả cached.
        cached = self.store.get_agent_output(article_id, raw_sha256)
        if cached and cached.get("dod_pass"):
            return {"ok": True, "article_id": article_id, "cached": True,
                    "dod_pass": True, "work_item_id": item["id"]}

        try:
            wp = self._load_work_package(item["package_path"])
        except (OSError, json.JSONDecodeError) as e:
            return {"ok": False, "article_id": article_id, "reason": f"package_unreadable: {e}"}

        # Preconditions (guardrail) rồi DoD.
        pre_ok, pre_reasons = verify_preconditions(wp)
        dod_ok, dod_reasons = (False, list(pre_reasons)) if not pre_ok else check_dod(output, wp)
        if not pre_ok:
            dod_ok = False

        pm = output.get("processing_metadata") or {}
        self.store.insert_agent_output({
            "article_id": article_id, "raw_sha256": raw_sha256,
            "work_item_id": item["id"],
            "output_json": json.dumps(output, ensure_ascii=False),
            "agent_provider": pm.get("agent_provider"),
            "model_used": pm.get("model_used"),
            "confidence": output.get("confidence"),
            "dod_pass": 1 if dod_ok else 0,
            "dod_reasons": json.dumps(dod_reasons, ensure_ascii=False),
            "created_at": now_vn_iso(),
        })

        if dod_ok:
            self.catalog.mark_done(item["id"])
        else:
            self.catalog.mark_failed(item["id"], f"dod_fail: {dod_reasons[:3]}")
        logger.info("[agent] ingest {} → dod_pass={} reasons={}",
                    article_id, dod_ok, dod_reasons[:3])
        return {"ok": dod_ok, "article_id": article_id, "work_item_id": item["id"],
                "dod_pass": dod_ok, "reasons": dod_reasons}
