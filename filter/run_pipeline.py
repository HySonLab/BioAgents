from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT = Path("/home/phpham/Work/BioAgents")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "search_config.json")
    parser.add_argument("--input-root", type=Path, default=ROOT / "data_raw/")
    args = parser.parse_args()
    commands = [
        [sys.executable, str(ROOT /'filter' / "01_combine.py"), "--input-root", str(args.input_root)],
        [sys.executable, str(ROOT /'filter'/ "02_filter.py"), "--config", str(args.config)],
        [sys.executable, str(ROOT /'filter'/ "03_deduplicate.py")],
        [sys.executable, str(ROOT /'filter'/ "04_assign_sort_export.py"), "--config", str(args.config)],
    ]
    for command in commands:
        print("RUNNING", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)

if __name__ == "__main__":
    main()
