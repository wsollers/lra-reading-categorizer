from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import APP_VERSION

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "categorizer.sqlite3"
TAXONOMY_PATH = ROOT / "taxonomy" / "subjects.yaml"
LRA_MAP_PATH = ROOT / "taxonomy" / "lra-volume-map.yaml"
READINGS_DIR = ROOT / "readings"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    if yaml:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return default if data is None else data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_filename_part(value: str, fallback: str = "untitled", max_len: int = 90) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text or fallback)[:max_len].rstrip(" .") or fallback


def managed_filename(title: str, author: str, source_id: str) -> str:
    title_part = clean_filename_part(title, "Untitled", 110)
    author_part = clean_filename_part(author, "unknown", 60)
    base = f"{title_part} -- {author_part} [{source_id}].pdf"
    if len(base) <= 180:
        return base
    title_part = title_part[:80].rstrip(" .")
    return f"{title_part} -- {author_part} [{source_id}].pdf"


def app_last_modified() -> str:
    paths = [Path(__file__), ROOT / "scripts" / "categorizer.py"]
    latest = max(path.stat().st_mtime for path in paths if path.exists())
    return datetime.fromtimestamp(latest).astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Category:
    main_slug: str
    main_label: str
    sub_slug: str
    sub_label: str


def load_categories(path: Path = TAXONOMY_PATH) -> list[Category]:
    data = load_yaml(path, {"subjects": []})
    categories: list[Category] = []
    for main in data.get("subjects") or []:
        main_slug = str(main.get("slug") or "")
        main_label = str(main.get("label") or main_slug)
        for child in main.get("children") or []:
            sub_slug = str(child.get("slug") or "")
            categories.append(Category(main_slug, main_label, sub_slug, str(child.get("label") or sub_slug)))
    return categories


def split_first_author(value: Any) -> str:
    authors = value or []
    if isinstance(authors, str):
        return authors
    if not authors:
        return ""
    first = authors[0]
    if isinstance(first, dict):
        return str(first.get("author_candidate_raw") or first.get("name") or "")
    return str(first or "")


def first_list_value(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def read_yaml_sources(path: Path) -> dict[str, dict[str, Any]]:
    data = load_yaml(path, {"sources": []})
    return {str(item.get("source_id")): item for item in data.get("sources") or [] if item.get("source_id")}


class CategorizerStore:
    def __init__(self, db_path: Path = DB_PATH, root: Path = ROOT) -> None:
        self.root = root
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def close(self) -> None:
        self.conn.close()

    def init_db(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS app_metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_pdfs (
              source_id TEXT PRIMARY KEY,
              sha256 TEXT NOT NULL,
              source_path TEXT NOT NULL,
              filename TEXT NOT NULL,
              page_count INTEGER,
              imported_at TEXT NOT NULL,
              duplicate_state TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS categorization_records (
              source_id TEXT PRIMARY KEY REFERENCES source_pdfs(source_id),
              title TEXT NOT NULL DEFAULT '',
              isbn TEXT NOT NULL DEFAULT '',
              first_author TEXT NOT NULL DEFAULT '',
              main_category TEXT NOT NULL DEFAULT '',
              sub_category TEXT NOT NULL DEFAULT '',
              lra_volume TEXT NOT NULL DEFAULT '',
              lra_book TEXT NOT NULL DEFAULT '',
              lra_chapter TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending',
              destination_path TEXT NOT NULL DEFAULT '',
              notes TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL,
              saved_at TEXT NOT NULL DEFAULT '',
              skipped_at TEXT NOT NULL DEFAULT '',
              copy_status TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS category_map (
              main_slug TEXT NOT NULL,
              sub_slug TEXT NOT NULL,
              lra_volume TEXT NOT NULL DEFAULT '',
              lra_book TEXT NOT NULL DEFAULT '',
              lra_chapter TEXT NOT NULL DEFAULT '',
              notes TEXT NOT NULL DEFAULT '',
              PRIMARY KEY(main_slug, sub_slug)
            );
            CREATE TABLE IF NOT EXISTS action_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_id TEXT NOT NULL,
              action TEXT NOT NULL,
              detail TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );
            """
        )
        self.conn.execute("INSERT OR REPLACE INTO app_metadata(key, value) VALUES ('version', ?)", [APP_VERSION])
        self.conn.execute("INSERT OR REPLACE INTO app_metadata(key, value) VALUES ('last_modified_at', ?)", [app_last_modified()])
        self.conn.commit()

    def seed_category_map(self, map_path: Path = LRA_MAP_PATH) -> int:
        data = load_yaml(map_path, {"mappings": []})
        count = 0
        for item in data.get("mappings") or []:
            self.conn.execute(
                """INSERT OR REPLACE INTO category_map(main_slug, sub_slug, lra_volume, lra_book, lra_chapter, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    item.get("main_slug") or "",
                    item.get("sub_slug") or "",
                    item.get("lra_volume") or "",
                    item.get("lra_book") or "",
                    item.get("lra_chapter") or "",
                    item.get("notes") or "",
                ],
            )
            count += 1
        self.conn.commit()
        return count

    def import_from_source_profiles(self, source_profiles: Path) -> dict[str, int]:
        db_path = source_profiles / "inventory" / "source-harness.sqlite3"
        if not db_path.exists():
            raise FileNotFoundError(db_path)
        bib = read_yaml_sources(source_profiles / "inventory" / "bibliography-candidates.yaml")
        subjects = read_yaml_sources(source_profiles / "inventory" / "subject-classification-candidates.yaml")
        local_bib = read_yaml_sources(source_profiles / "inventory" / "local-bib-verification.yaml")
        imported = updated = skipped = 0
        source_conn = sqlite3.connect(db_path)
        source_conn.row_factory = sqlite3.Row
        try:
            rows = source_conn.execute(
                """SELECT source_id, sha256, current_path, filename, page_count, state, duplicate_of_source_id
                   FROM files
                   WHERE duplicate_of_source_id IS NULL
                     AND state NOT IN ('QUARANTINE_CANDIDATE', 'QUARANTINED', 'EXACT_DUPLICATE')
                   ORDER BY source_id"""
            ).fetchall()
        finally:
            source_conn.close()
        now = utc_now()
        for row in rows:
            source_id = str(row["source_id"])
            path = Path(str(row["current_path"]))
            if not path.exists():
                skipped += 1
                continue
            bib_row = bib.get(source_id, {})
            subject_row = subjects.get(source_id, {})
            local_row = local_bib.get(source_id, {})
            best_match = local_row.get("best_match") or {}
            title = str(bib_row.get("canonical_title_candidate") or subject_row.get("canonical_title_candidate") or best_match.get("title") or path.stem)
            isbn = first_list_value(bib_row.get("valid_isbn") or (best_match.get("isbn") or []))
            author = split_first_author(bib_row.get("author_candidates") or best_match.get("authors") or [])
            main_category, sub_category = self.suggest_taxonomy(subject_row, local_row)
            self.conn.execute(
                """INSERT OR REPLACE INTO source_pdfs(source_id, sha256, source_path, filename, page_count, imported_at, duplicate_state)
                   VALUES (?, ?, ?, ?, ?, COALESCE((SELECT imported_at FROM source_pdfs WHERE source_id = ?), ?), '')""",
                [source_id, row["sha256"], str(path), row["filename"], row["page_count"], source_id, now],
            )
            existing = self.conn.execute("SELECT status FROM categorization_records WHERE source_id = ?", [source_id]).fetchone()
            if existing:
                self.conn.execute(
                    """UPDATE categorization_records
                       SET title = CASE WHEN status = 'pending' THEN ? ELSE title END,
                           isbn = CASE WHEN status = 'pending' THEN ? ELSE isbn END,
                           first_author = CASE WHEN status = 'pending' THEN ? ELSE first_author END,
                           main_category = CASE WHEN status = 'pending' THEN ? ELSE main_category END,
                           sub_category = CASE WHEN status = 'pending' THEN ? ELSE sub_category END,
                           updated_at = ?
                       WHERE source_id = ?""",
                    [title, isbn, author, main_category, sub_category, now, source_id],
                )
                updated += 1
            else:
                self.conn.execute(
                    """INSERT INTO categorization_records(source_id, title, isbn, first_author, main_category, sub_category, status, updated_at, notes)
                       VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    [source_id, title, isbn, author, main_category, sub_category, now, self.import_notes(subject_row, local_row)],
                )
                imported += 1
        self.seed_category_map()
        self.conn.commit()
        return {"imported": imported, "updated": updated, "skipped_missing": skipped, "total_canonical": len(rows)}

    def import_notes(self, subject_row: dict[str, Any], local_row: dict[str, Any]) -> str:
        bits = []
        if subject_row.get("primary_subject"):
            bits.append(f"classifier={subject_row.get('primary_subject')}")
        best = local_row.get("best_match") or {}
        if best.get("bib_path"):
            bits.append(f"local_bib={Path(str(best.get('bib_path'))).stem}")
        if subject_row.get("review_flags"):
            bits.append("flags=" + ";".join(subject_row.get("review_flags") or []))
        return " | ".join(bits)

    def suggest_taxonomy(self, subject_row: dict[str, Any], local_row: dict[str, Any]) -> tuple[str, str]:
        primary = str(subject_row.get("primary_subject") or "")
        mapping = {
            "logic-model-theory": ("00-foundations", "mathematical-logic"),
            "set-theory": ("00-foundations", "set-theory"),
            "category-theory": ("00-foundations", "category-theory"),
            "abstract-algebra": ("01-algebra", "abstract-algebra"),
            "linear-algebra": ("01-algebra", "linear-algebra"),
            "calculus": ("03-analysis", "calculus"),
            "real-analysis": ("03-analysis", "real-analysis"),
            "measure-theory": ("03-analysis", "measure-theory"),
            "functional-analysis": ("03-analysis", "functional-analysis"),
            "complex-analysis": ("03-analysis", "complex-analysis"),
            "topology": ("04-topology-and-geometry", "point-set-topology"),
            "geometry": ("04-topology-and-geometry", "euclidean-and-classical-geometry"),
            "differential-geometry": ("04-topology-and-geometry", "differential-geometry"),
            "ode-dynamical-systems": ("05-differential-equations-and-dynamical-systems", "ordinary-differential-equations"),
            "partial-differential-equations": ("05-differential-equations-and-dynamical-systems", "partial-differential-equations"),
            "probability": ("06-probability-statistics-and-information", "probability-theory"),
            "stochastic-calculus": ("06-probability-statistics-and-information", "stochastic-calculus"),
            "combinatorics-graph-theory": ("07-discrete-mathematics-and-combinatorics", "combinatorics"),
            "numerical-analysis": ("08-applied-and-computational-mathematics", "numerical-analysis"),
            "theoretical-computer-science": ("09-theoretical-computer-science", "automata-and-formal-languages"),
        }
        if primary in mapping:
            return mapping[primary]
        return "11-reference-and-miscellaneous", "uncategorized"

    def queue_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM source_pdfs").fetchone()[0])

    def processed_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM categorization_records WHERE status IN ('saved', 'skipped')").fetchone()[0])

    def current_pending(self) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT s.*, c.*
               FROM source_pdfs s JOIN categorization_records c USING(source_id)
               WHERE c.status = 'pending'
               ORDER BY s.source_id
               LIMIT 1"""
        ).fetchone()

    def record_at_offset(self, offset: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT s.*, c.*
               FROM source_pdfs s JOIN categorization_records c USING(source_id)
               WHERE c.status = 'pending'
               ORDER BY s.source_id
               LIMIT 1 OFFSET ?""",
            [max(0, offset)],
        ).fetchone()

    def category_target(self, main_slug: str, sub_slug: str) -> Path:
        return READINGS_DIR / main_slug / sub_slug

    def lra_mapping_for(self, main_slug: str, sub_slug: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM category_map WHERE main_slug = ? AND sub_slug = ?", [main_slug, sub_slug]).fetchone()

    def save_record(self, source_id: str, title: str, isbn: str, first_author: str, main_category: str, sub_category: str, notes: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM source_pdfs WHERE source_id = ?", [source_id]).fetchone()
        if not row:
            raise ValueError(f"unknown source_id: {source_id}")
        source = Path(str(row["source_path"]))
        if not source.exists():
            raise FileNotFoundError(source)
        if sha256(source) != str(row["sha256"]):
            raise ValueError("source SHA mismatch")
        target_dir = self.category_target(main_category, sub_category)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / managed_filename(title, first_author, source_id)
        copy_status = "copied"
        if destination.exists():
            if not destination.is_file():
                raise ValueError("destination exists and is not a file")
            if sha256(destination) != str(row["sha256"]):
                raise FileExistsError(f"destination exists with different SHA: {destination}")
            copy_status = "already_materialized"
        else:
            shutil.copy2(source, destination)
            if sha256(destination) != str(row["sha256"]):
                raise ValueError("destination SHA mismatch after copy")
        mapping = self.lra_mapping_for(main_category, sub_category)
        now = utc_now()
        self.conn.execute(
            """UPDATE categorization_records
               SET title = ?, isbn = ?, first_author = ?, main_category = ?, sub_category = ?,
                   lra_volume = ?, lra_book = ?, lra_chapter = ?, status = 'saved',
                   destination_path = ?, notes = ?, updated_at = ?, saved_at = ?, copy_status = ?
               WHERE source_id = ?""",
            [
                title,
                isbn,
                first_author,
                main_category,
                sub_category,
                mapping["lra_volume"] if mapping else "",
                mapping["lra_book"] if mapping else "",
                mapping["lra_chapter"] if mapping else "",
                str(destination),
                notes,
                now,
                now,
                copy_status,
                source_id,
            ],
        )
        self.conn.execute("INSERT INTO action_log(source_id, action, detail, created_at) VALUES (?, 'save', ?, ?)", [source_id, copy_status, now])
        self.conn.commit()
        return {"destination": str(destination), "copy_status": copy_status}

    def skip_record(self, source_id: str, notes: str = "") -> None:
        now = utc_now()
        self.conn.execute(
            """UPDATE categorization_records
               SET status = 'skipped', notes = ?, updated_at = ?, skipped_at = ?
               WHERE source_id = ?""",
            [notes, now, now, source_id],
        )
        self.conn.execute("INSERT INTO action_log(source_id, action, detail, created_at) VALUES (?, 'skip', ?, ?)", [source_id, notes, now])
        self.conn.commit()


def open_pdf_in_chrome(pdf_path: Path, chrome_path: Path | None = None) -> subprocess.Popen[Any] | None:
    target = pdf_path.resolve().as_uri()
    profile_dir = ROOT / "data" / "chrome-pdf-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        "--new-window",
        "--no-first-run",
        "--disable-extensions",
        f"--user-data-dir={profile_dir}",
        target,
    ]
    if chrome_path:
        return subprocess.Popen([str(chrome_path), *args])
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return subprocess.Popen([str(candidate), *args])
    if sys.platform.startswith("win"):
        return subprocess.Popen(["cmd", "/c", "start", "", target])
    else:
        return subprocess.Popen(["xdg-open", target])


def export_review_csv(store: CategorizerStore, path: Path) -> int:
    rows = store.conn.execute(
        """SELECT s.source_id, s.filename, s.source_path, c.title, c.isbn, c.first_author,
                  c.main_category, c.sub_category, c.status, c.destination_path, c.notes,
                  c.updated_at, c.copy_status
           FROM source_pdfs s JOIN categorization_records c USING(source_id)
           ORDER BY s.source_id"""
    ).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = rows[0].keys() if rows else [
        "source_id", "filename", "source_path", "title", "isbn", "first_author",
        "main_category", "sub_category", "status", "destination_path", "notes",
        "updated_at", "copy_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    return len(rows)
