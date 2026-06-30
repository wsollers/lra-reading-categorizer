from __future__ import annotations

import shutil
import sqlite3
import sys
import uuid
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reading_categorizer import core
from reading_categorizer.core import CategorizerStore, sha256


class CategorizerTests(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(__file__).resolve().parents[1] / "tmp" / "tests"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = base / f"case-{uuid.uuid4().hex}"
        self.tmp.mkdir()
        self.original_readings = core.READINGS_DIR
        core.READINGS_DIR = self.tmp / "readings"
        core.READINGS_DIR.mkdir()

    def tearDown(self) -> None:
        core.READINGS_DIR = self.original_readings
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_store_with_source(self) -> tuple[CategorizerStore, Path]:
        source = self.tmp / "source.pdf"
        source.write_bytes(b"%PDF test bytes")
        store = CategorizerStore(self.tmp / "state.sqlite3", root=self.tmp)
        now = core.utc_now()
        store.conn.execute(
            """INSERT INTO source_pdfs(source_id, sha256, source_path, filename, page_count, imported_at)
               VALUES ('SRC-1', ?, ?, 'source.pdf', 120, ?)""",
            [sha256(source), str(source), now],
        )
        store.conn.execute(
            """INSERT INTO categorization_records(source_id, title, isbn, first_author, main_category, sub_category, status, updated_at)
               VALUES ('SRC-1', 'A Title', '123', 'Ada', '03-analysis', 'real-analysis', 'pending', ?)""",
            [now],
        )
        store.conn.commit()
        return store, source

    def test_save_copies_pdf_and_marks_processed(self) -> None:
        store, source = self.make_store_with_source()
        try:
            result = store.save_record("SRC-1", "A Title", "123", "Ada", "03-analysis", "real-analysis", "")
            destination = Path(result["destination"])
            self.assertTrue(source.exists())
            self.assertTrue(destination.exists())
            self.assertEqual(sha256(source), sha256(destination))
            row = store.conn.execute("SELECT status, copy_status FROM categorization_records WHERE source_id = 'SRC-1'").fetchone()
            self.assertEqual(row["status"], "saved")
            self.assertEqual(row["copy_status"], "copied")
        finally:
            store.close()

    def test_save_is_idempotent_for_same_sha_destination(self) -> None:
        store, _ = self.make_store_with_source()
        try:
            first = store.save_record("SRC-1", "A Title", "123", "Ada", "03-analysis", "real-analysis", "")
            store.conn.execute("UPDATE categorization_records SET status = 'pending' WHERE source_id = 'SRC-1'")
            store.conn.commit()
            second = store.save_record("SRC-1", "A Title", "123", "Ada", "03-analysis", "real-analysis", "")
            self.assertEqual(first["destination"], second["destination"])
            self.assertEqual(second["copy_status"], "already_materialized")
        finally:
            store.close()

    def test_save_refuses_different_sha_destination(self) -> None:
        store, _ = self.make_store_with_source()
        try:
            target_dir = core.READINGS_DIR / "03-analysis" / "real-analysis"
            target_dir.mkdir(parents=True)
            destination = target_dir / core.managed_filename("A Title", "Ada", "SRC-1")
            destination.write_bytes(b"different")
            with self.assertRaises(FileExistsError):
                store.save_record("SRC-1", "A Title", "123", "Ada", "03-analysis", "real-analysis", "")
        finally:
            store.close()

    def test_skip_is_persistent(self) -> None:
        store, _ = self.make_store_with_source()
        try:
            store.skip_record("SRC-1", "later")
            self.assertIsNone(store.current_pending())
            row = store.conn.execute("SELECT status, notes FROM categorization_records WHERE source_id = 'SRC-1'").fetchone()
            self.assertEqual(row["status"], "skipped")
            self.assertEqual(row["notes"], "later")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
