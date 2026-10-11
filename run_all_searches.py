from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent

SCRIPTS = {source: ROOT / "crawl_data" / f"search_{source}.py" for source in ( "arxiv", "europe_pmc", "pubmed" )}
def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default=str(ROOT / "config" / "search_config.json")); parser.add_argument("--sources", nargs="+", choices=SCRIPTS, default=list(SCRIPTS)); args = parser.parse_args()
    failures = []
    try:
        for source in args.sources:
            command = [sys.executable, str(SCRIPTS[source]), "--config", args.config]
            print("\nRUNNING", " ".join(command), flush=True)
            result = subprocess.run(command, cwd=ROOT)
            if result.returncode: failures.append((source, result.returncode))
    except KeyboardInterrupt:
        print("\nInterrupted. Completed domain files are preserved."); return 130
    return 1 if failures else 0
if __name__ == "__main__": raise SystemExit(main())
