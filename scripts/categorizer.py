from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reading_categorizer.core import DB_PATH, CategorizerStore, export_review_csv
from reading_categorizer.gui import CategorizerApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual LRA reading categorizer.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-db")
    init.add_argument("--source-profiles", type=Path)

    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("--source-profiles", type=Path, default=Path(r"F:\repos\lra-source-profiles"))

    gui = sub.add_parser("gui")
    gui.add_argument("--chrome-path", type=Path)

    export = sub.add_parser("export")
    export.add_argument("--out", type=Path, default=Path("review/categorization-progress.csv"))

    sub.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = CategorizerStore(args.db)
    try:
        if args.command == "init-db":
            mapped = store.seed_category_map()
            print(f"category_mappings={mapped}")
            if args.source_profiles:
                result = store.import_from_source_profiles(args.source_profiles)
                print(f"imported={result['imported']}")
                print(f"updated={result['updated']}")
                print(f"skipped_missing={result['skipped_missing']}")
                print(f"total_canonical={result['total_canonical']}")
        elif args.command == "import":
            result = store.import_from_source_profiles(args.source_profiles)
            print(f"imported={result['imported']}")
            print(f"updated={result['updated']}")
            print(f"skipped_missing={result['skipped_missing']}")
            print(f"total_canonical={result['total_canonical']}")
        elif args.command == "gui":
            app = CategorizerApp(store, args.chrome_path)
            app.mainloop()
        elif args.command == "export":
            count = export_review_csv(store, args.out)
            print(f"exported={count}")
            print(f"path={args.out}")
        elif args.command == "status":
            print(f"total={store.queue_count()}")
            print(f"processed={store.processed_count()}")
            pending = store.current_pending()
            print(f"next_source_id={pending['source_id'] if pending else ''}")
        else:
            raise ValueError(args.command)
        return 0
    finally:
        if args.command != "gui":
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
