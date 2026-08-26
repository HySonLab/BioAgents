from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, re, unicodedata

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
LOGS = ROOT / "logs"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_config(path=None):
    path = Path(path or ROOT / "config" / "search_config.json")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if "REPLACE_WITH" in cfg.get("contact_email", ""):
        raise ValueError("Edit config/search_config.json and provide a real contact_email.")
    if "REPLACE_WITH" in cfg.get("crossref_mailto", ""):
        raise ValueError("Edit config/search_config.json and provide a real crossref_mailto.")
    return cfg


def ensure_dirs():
    RAW.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)


def normalize_title(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def normalize_doi(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(".,; ")


def stable_search_id(source, mode, domain, query):
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
    return f"{source}-{mode}-{domain}-{digest}".upper().replace("_", "-")


def write_rows(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows and not fieldnames:
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def append_log(row):
    path = LOGS / "search_log.csv"
    exists = path.exists()
    fields = [
        "search_id", "source", "search_date_utc", "query_mode", "domain_group",
        "query_exact", "date_from", "date_until", "results_reported",
        "records_downloaded", "raw_file", "csv_file", "status", "notes"
    ]
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})


def save_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def quote_term(term):
    return f'"{term}"' if " " in term else term


def build_concept_queries(cfg):
    agent_block = " OR ".join(quote_term(t) for t in cfg["agent_terms"])
    eval_block = " OR ".join(quote_term(t) for t in cfg["evaluation_terms"])
    for mode in cfg["query_modes"]:
        for domain, terms in cfg["domain_groups"].items():
            domain_block = " OR ".join(quote_term(t) for t in terms)
            base = f"({agent_block}) AND ({domain_block})"
            query = base if mode == "systems" else f"{base} AND ({eval_block})"
            yield mode, domain, query
