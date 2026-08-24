"""
Unit tests for News-Scape Harness CLI (H2-H5).
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add repo root to sys.path
import sys
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.harness_cli import (
    init_db,
    query_contract,
    query_matrix,
    cmd_intake,
    cmd_story_add,
    cmd_story_update,
    cmd_story_complete,
    cmd_decision_add,
    cmd_backlog_add,
    cmd_backlog_close,
    cmd_trace,
    cmd_audit,
    cmd_propose,
    calculate_score_trace,
    calculate_score_context,
)
import argparse


class TestHarnessCLI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_harness.db")
        self.schema_dir = str(ROOT_DIR / "scripts" / "schema")
        
        # Init DB
        res = init_db(self.db_path, self.schema_dir)
        self.assertEqual(res["status"], "success")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_query_contract(self):
        contract = query_contract(self.db_path)
        self.assertEqual(contract["protocol_version"], "harness-orchestration-v1")
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["database_state"], "ready")
        self.assertIn("intake", contract["capabilities"])
        self.assertIn("audit", contract["capabilities"])
        self.assertIn("propose", contract["capabilities"])

    def test_intake_and_story_lifecycle(self):
        # 1. Intake
        intake_args = argparse.Namespace(
            db=self.db_path,
            type="maintenance",
            summary="Refactor deduplication cache",
            lane="normal",
            flags="[]",
            story="US-099"
        )
        intake_res = cmd_intake(intake_args)
        self.assertEqual(intake_res["status"], "success")
        intake_id = intake_res["intake_id"]
        self.assertGreater(intake_id, 0)

        # 2. Add Story
        story_args = argparse.Namespace(
            db=self.db_path,
            id="US-099",
            title="Refactor dedup cache",
            parent="Performance Epic",
            status="planned",
            lane="normal",
            contract="Fast memory cache",
            criteria="Pass all dedup tests",
            verify_cmd="python -c \"print('OK')\""
        )
        s_add = cmd_story_add(story_args)
        self.assertEqual(s_add["status"], "success")

        # 3. Update Story to in_progress
        up_args = argparse.Namespace(
            db=self.db_path,
            id="US-099",
            title=None,
            parent=None,
            status="in_progress",
            lane=None,
            unit_proof=None,
            integ_proof=None,
            e2e_proof=None,
            platform_proof=None,
            evidence=None,
            verify_cmd=None
        )
        s_up = cmd_story_update(up_args)
        self.assertEqual(s_up["status"], "success")

        # 4. Attempt to complete WITHOUT proof (Should fail per Golden Rule)
        comp_args_fail = argparse.Namespace(
            db=self.db_path,
            id="US-099",
            unit_proof=0,
            integ_proof=0,
            e2e_proof=0,
            platform_proof=0,
            evidence=None,
            verify_cmd=None,
            run_verify=False
        )
        res_fail = cmd_story_complete(comp_args_fail)
        self.assertEqual(res_fail["status"], "error")
        self.assertEqual(res_fail["error_code"], "NO_PROOF")

        # 5. Complete WITH proof
        comp_args = argparse.Namespace(
            db=self.db_path,
            id="US-099",
            unit_proof=1,
            integ_proof=1,
            e2e_proof=0,
            platform_proof=0,
            evidence="12/12 unit tests passed",
            verify_cmd="python -c \"print('Verified')\"",
            run_verify=True
        )
        res_pass = cmd_story_complete(comp_args)
        self.assertEqual(res_pass["status"], "success")
        self.assertEqual(res_pass["status_to"], "implemented")

        # 6. Verify Matrix Query
        matrix = query_matrix(self.db_path)
        self.assertEqual(matrix["total"], 1)
        self.assertEqual(matrix["counts"]["implemented"], 1)

    def test_trace_and_scoring(self):
        # Record trace
        trace_args = argparse.Namespace(
            db=self.db_path,
            summary="Refactored database pool with WAL mode",
            story=None,
            intake=None,
            outcome="completed",
            actions='["Configured PRAGMA", "Verified connection pooling"]',
            files_read='["project/src/db/store.py", "project/src/db/writer.py"]',
            files_changed='["project/src/db/store.py"]',
            lane="normal",
            friction="None",
            error=None
        )
        tr_res = cmd_trace(trace_args)
        self.assertEqual(tr_res["status"], "success")
        self.assertEqual(tr_res["score_trace"], 1.0)
        self.assertEqual(tr_res["score_context"], 1.0)

    def test_decision_and_backlog(self):
        # Decision
        dec_args = argparse.Namespace(
            db=self.db_path,
            id="0001-test-decision",
            title="Test Decision",
            status="accepted",
            doc_path="docs/decisions/0001-test.md",
            impact="Improved stability",
            outcome="Successful"
        )
        dec_res = cmd_decision_add(dec_args)
        self.assertEqual(dec_res["status"], "success")

        # Backlog Add
        b_add_args = argparse.Namespace(
            db=self.db_path,
            title="Investigate OneDrive lock on Windows",
            pain="Permissions error during batch write",
            suggested="Use safe_atomic_write",
            lane="normal",
            component="durable_io",
            discovered_while="Live scraping"
        )
        b_res = cmd_backlog_add(b_add_args)
        self.assertEqual(b_res["status"], "success")
        backlog_id = b_res["backlog_id"]

        # Backlog Close
        b_close_args = argparse.Namespace(
            db=self.db_path,
            id=backlog_id,
            outcome="Fixed by atomic staging module"
        )
        b_close_res = cmd_backlog_close(b_close_args)
        self.assertEqual(b_close_res["status"], "success")

    def test_audit_and_propose(self):
        # Audit on clean DB
        audit_res = cmd_audit(self.db_path)
        self.assertEqual(audit_res["status"], "success")
        self.assertGreaterEqual(audit_res["health_score"], 0.9)
        self.assertLessEqual(audit_res["entropy_score"], 0.1)

        # Propose
        propose_res = cmd_propose(self.db_path)
        self.assertEqual(propose_res["status"], "success")


if __name__ == "__main__":
    unittest.main()
