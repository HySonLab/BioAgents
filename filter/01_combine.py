from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from pipeline_common import DATA_RAW, DATA_OUT, REPORTS, canonicalize


def discover(root: Path) -> list[Path]:
    paths = []
    for path in root.rglob("*.csv"):
        name = path.name.lower()
        parts = {part.lower() for part in path.parts}
        if "chunks" in parts:
            continue
        if "rejected" in name or "audit" in name or "checkpoint" in name:
            continue
        paths.append(path)
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=DATA_RAW)
    args = parser.parse_args()
    paths = discover(args.input_root)
    if not paths:
        raise RuntimeError(f"No eligible CSV files found under {args.input_root}")
    frames, manifest = [], []
    for path in paths:
        try:
            raw = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
        except (pd.errors.EmptyDataError, UnicodeDecodeError):
            continue
        if raw.empty:
            continue
        frame = canonicalize(raw)
        frame["retrieval_file"] = str(path)
        frames.append(frame)
        manifest.append({"file": str(path), "input_rows": len(raw), "source_values": "; ".join(sorted(set(frame["source"])))})
    if not frames:
        raise RuntimeError("All discovered CSV files were empty or unreadable")
    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    combined.to_csv(DATA_OUT / "01_combined_source_rows.csv", index=False)
    pd.DataFrame(manifest).to_csv(REPORTS / "input_file_manifest.csv", index=False)
    print(f"Combined {len(combined):,} rows from {len(frames):,} files")

if __name__ == "__main__":
    main()
