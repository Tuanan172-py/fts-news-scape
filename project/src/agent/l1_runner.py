"""Bộ điều phối thực thi nhận diện thực thể tầng L1."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.agent.l1_classifier import classify_title
from src.agent.l1_router import (
    CODE_FIRST_PROVIDER, build_code_first_output, build_l1_task_packet, check_l1_dod,
    route_article, write_l1_packet,
)
from src.core.models import now_vn_iso


class L1Runner:
    """Điều phối quy trình nhận diện thực thể tầng L1 và xử lý kết quả.

    Attributes:
        store: Kho dữ liệu cơ sở SQLite hoặc tương đương.
        task_dir: Thư mục lưu trữ các gói công việc L1 dạng tệp JSON.
        reg: Sổ đăng ký thực thể EntityRegistry.
    """

    def __init__(self, store, registry=None, *, task_dir: str = "data/agent_tasks/l1"):
        """Khởi tạo bộ điều phối L1Runner.

        Args:
            store: Kho dữ liệu cơ sở lưu trữ bài viết và tác vụ.
            registry: Sổ đăng ký thực thể tùy chọn. Mặc định tự nạp qua load_registry().
            task_dir: Thư mục lưu trữ các tệp gói công việc L1.
        """
        self.store = store
        self.task_dir = task_dir
        if registry is None:
            from src.agent.entities import load_registry
            registry = load_registry()
        self.reg = registry

    # -- producer: code-first → l1_tasks + packet -----------------------------
    def route_and_export(self, article: dict, *, review: str = "all") -> dict:
        """Phân loại thực thể tự động, lưu tác vụ và tạo tệp gói công việc.

        Args:
            article: Dữ liệu bài viết cần xử lý.
            review: Chế độ xuất gói công việc ('all' hoặc 'missed').

        Returns:
            Từ điển kết quả phân loại kèm đường dẫn gói công việc nếu có.
        """
        rec = route_article(article, self.reg)
        aid = article.get("article_id")
        emit = review == "all" or (review == "missed" and rec["route"] == "needs_agent")

        packet_path = None
        if emit:
            packet = build_l1_task_packet(article, rec)
            packet_path = write_l1_packet(packet, base_dir=self.task_dir)

        self.store.upsert_l1_task({
            "article_id": aid,
            "domain": article.get("domain"),
            "title": rec["title"],
            "code_first_json": json.dumps(rec, ensure_ascii=False),
            "route": rec["route"],
            "packet_path": packet_path,
            "enqueued_at": now_vn_iso(),
        })
        rec["packet_path"] = packet_path
        return rec

    # -- producer 2: vat chat hoa ban TAT DINH -> l1_outputs ------------------
    def ingest_code_first(self, task: dict) -> dict:
        """Vật chất hóa kết quả phân loại tự động thành bản ghi đầu ra L1 chuẩn.

        Args:
            task: Dữ liệu bản ghi tác vụ từ bảng l1_tasks.

        Returns:
            Từ điển kết quả xử lý gồm trạng thái hợp lệ, mã bài viết và danh sách lỗi.
        """
        aid = task["article_id"]
        title = task.get("title") or ""

        # Uu tien articles.title — do LA tieu de nguoi dung nhan duoc. Voi 122/1320 bai
        # (chu yeu trang cong bo thong tin cua cafef) tieu de Silver lai la header trang ho so
        # doanh nghiep ("Ngan hang TMCP Phat trien T.P Ho Chi Minh (HOSE)") trong khi bai that
        # la "HDB: Thong bao thay doi dia diem...". Nhan dien tren tieu de sai vua lam MAT ma
        # (HDB khop ngay bang code o tieu de that) vua khien `surface` khong the kiem chung
        # duoc tren ban giao cho nguoi dung. Nguyen nhan goc nam o Silver title extraction.
        art = self.store.get_by_hash(aid)
        art_title = (getattr(art, "title", None) or "").strip() if art else ""
        if art_title and art_title != title:
            title = art_title
            task = {**task, "title": title}

        rec = classify_title(title, self.reg)
        rec["article_id"] = aid
        rec["domain"] = task.get("domain")

        if not (rec.get("entity_ids") or []):
            # Matcher moi khong con khop gi — gan nhu chac chan ban cu khop nham. Khong ghi
            # ban recognized=false (se khoa task o 'done' vinh vien), ma tra ve cho Agent.
            self.store.upsert_l1_task({
                "article_id": aid, "domain": task.get("domain"), "title": title,
                "code_first_json": json.dumps(rec, ensure_ascii=False),
                "route": "needs_agent", "packet_path": task.get("packet_path"),
                "enqueued_at": task.get("enqueued_at") or now_vn_iso(),
            })
            return {"ok": False, "article_id": aid, "reason": "no_entity_after_recheck"}

        # Dong bo lai title vao l1_tasks: DoD grounding va ban giao cho nguoi dung phai
        # kiem chung tren CUNG mot tieu de.
        if (task.get("title") or "") != (self.store.get_l1_task(aid) or {}).get("title"):
            self.store.upsert_l1_task({
                "article_id": aid, "domain": task.get("domain"), "title": title,
                "code_first_json": json.dumps(rec, ensure_ascii=False),
                "route": "resolved", "packet_path": task.get("packet_path"),
                "enqueued_at": task.get("enqueued_at") or now_vn_iso(),
            })

        output = build_code_first_output(rec, aid)
        ok, reasons = check_l1_dod(output, title, self.reg)
        self.store.insert_l1_output({
            "article_id": aid,
            "output_json": json.dumps(output, ensure_ascii=False),
            "recognized": 1,
            "agent_provider": CODE_FIRST_PROVIDER,
            "model_used": output["processing_metadata"]["model_used"],
            "confidence": None,          # tra bang -> khong tu cham diem tin cay
            "dod_pass": 1 if ok else 0,
            "dod_reasons": json.dumps(reasons, ensure_ascii=False),
            "created_at": now_vn_iso(),
            "l1_source": CODE_FIRST_PROVIDER,
        })
        if ok:
            self.store.set_l1_status(aid, "done", done_at=now_vn_iso())
        else:
            self.store.set_l1_status(aid, "failed", error=json.dumps(reasons[:3], ensure_ascii=False))
        return {"ok": ok, "article_id": aid, "dod_pass": ok, "reasons": reasons,
                "entity_ids": rec["entity_ids"]}

    def drain_code_first(self, *, limit: int | None = None, dry_run: bool = False) -> dict:
        """Xử lý toàn bộ các tác vụ phân loại tự động đang ở trạng thái chờ.

        Args:
            limit: Giới hạn số lượng tác vụ xử lý tối đa.
            dry_run: Nếu True, chỉ thống kê và kiểm tra mà không ghi cơ sở dữ liệu.

        Returns:
            Từ điển thống kê số lượng bản ghi đã quét, thành công, lỗi hoặc chuyển tuyến.
        """
        conn = self.store.connect()
        try:
            sql = ("SELECT * FROM l1_tasks WHERE route = 'resolved' AND status = 'pending' "
                   "ORDER BY enqueued_at DESC")
            if limit:
                sql += f" LIMIT {int(limit)}"
            tasks = [dict(r) for r in conn.execute(sql)]
        finally:
            conn.close()

        stat = {"scanned": len(tasks), "written": 0, "dod_fail": 0, "rerouted": 0}
        if dry_run:
            for t in tasks:
                rec = classify_title(t.get("title") or "", self.reg)
                if not (rec.get("entity_ids") or []):
                    stat["rerouted"] += 1
                    continue
                out = build_code_first_output(rec, t["article_id"])
                ok, _ = check_l1_dod(out, t.get("title") or "", self.reg)
                stat["written" if ok else "dod_fail"] += 1
            return stat
        for t in tasks:
            r = self.ingest_code_first(t)
            if r.get("reason") == "no_entity_after_recheck":
                stat["rerouted"] += 1
            elif r["ok"]:
                stat["written"] += 1
            else:
                stat["dod_fail"] += 1
        logger.info("[l1/code-first] {}", stat)
        return stat

    # -- consumer: agent output → validate + DoD → mark -----------------------
    def ingest_output(self, output: dict | str) -> dict:
        """Tiếp nhận, kiểm tra chuẩn DoD và lưu kết quả từ agent.

        Args:
            output: Từ điển dữ liệu hoặc đường dẫn tệp JSON chứa kết quả phân tích của agent.

        Returns:
            Từ điển thông báo trạng thái xử lý và kết quả kiểm định DoD.
        """
        if isinstance(output, str):
            output = json.loads(Path(output).read_text(encoding="utf-8"))
        aid = output.get("article_id")
        if not aid:
            return {"ok": False, "reason": "missing article_id"}

        task = self.store.get_l1_task(aid)
        if task is None:
            return {"ok": False, "article_id": aid, "reason": "no l1_task"}

        # Idempotent replay — da co output AGENT dat DoD thi tra cached.
        cached = self.store.get_l1_output(aid)
        if cached and cached.get("dod_pass") and cached.get("l1_source", "agent") != CODE_FIRST_PROVIDER:
            return {"ok": True, "article_id": aid, "cached": True, "dod_pass": True}
        # Ban code_first la TAM: agent co quyen ghi de (chieu nguoc lai thi khong).
        # docs/decisions/0003-code-first-l1-delivery.md

        title = task.get("title") or ""
        ok, reasons = check_l1_dod(output, title)

        pm = output.get("processing_metadata") or {}
        self.store.insert_l1_output({
            "article_id": aid,
            "output_json": json.dumps(output, ensure_ascii=False),
            "recognized": 1 if output.get("recognized") else 0,
            "agent_provider": pm.get("agent_provider"),
            "model_used": pm.get("model_used"),
            "confidence": output.get("confidence"),
            "dod_pass": 1 if ok else 0,
            "dod_reasons": json.dumps(reasons, ensure_ascii=False),
            "created_at": now_vn_iso(),
        })
        if ok:
            self.store.set_l1_status(aid, "done", done_at=now_vn_iso())
        else:
            self.store.set_l1_status(aid, "failed", error=json.dumps(reasons[:3], ensure_ascii=False))
        logger.info("[l1] ingest {} → dod_pass={} reasons={}", aid, ok, reasons[:3])
        return {"ok": ok, "article_id": aid, "dod_pass": ok, "reasons": reasons}
