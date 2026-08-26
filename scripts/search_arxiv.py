from __future__ import annotations

import argparse
import time
import urllib.parse

from datetime import datetime, time as dt_time, timezone

import requests
import feedparser

from dateutil.parser import parse as dtparse

from common import *


URL = "https://export.arxiv.org/api/query"


def ensure_utc(value):
    """Return a timezone-aware datetime normalized to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def arxiv_query(generic):
    tokens = re.findall(
        r'"[^"]+"|\bAND\b|\bOR\b|\(|\)|[^\s()]+',
        generic,
    )

    output = []

    for token in tokens:
        if token in {"AND", "OR", "(", ")"}:
            output.append(token)
        else:
            output.append("all:" + token)

    return " ".join(output)


def run(cfg):
    ensure_dirs()

    session = requests.Session()
    session.headers["User-Agent"] = (
        f"FEV-evidence-map/1.0 ({cfg['contact_email']})"
    )

    date_from = datetime.strptime(
        cfg["date_from"],
        "%Y-%m-%d",
    ).date()

    date_until = datetime.strptime(
        cfg["date_until"],
        "%Y-%m-%d",
    ).date()

    d0 = datetime.combine(
        date_from,
        dt_time.min,
        tzinfo=timezone.utc,
    )

    d1 = datetime.combine(
        date_until,
        dt_time.max,
        tzinfo=timezone.utc,
    )

    for mode, domain, generic in build_concept_queries(cfg):
        query = arxiv_query(generic)
        sid = stable_search_id(
            "arxiv",
            mode,
            domain,
            query,
        )

        start = 0
        batch = 100
        rows = []
        total = None
        raw_files = []

        while len(rows) < cfg["max_records_per_query"]:
            params = {
                "search_query": query,
                "start": start,
                "max_results": batch,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            response = session.get(
                URL,
                params=params,
                timeout=120,
            )
            response.raise_for_status()

            raw_path = (
                RAW
                / "arxiv"
                / f"{sid}_{start:06d}.xml"
            )
            raw_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            raw_path.write_bytes(response.content)
            raw_files.append(str(raw_path))

            feed = feedparser.parse(response.content)

            if total is None:
                total = int(
                    feed.feed.get(
                        "opensearch_totalresults",
                        0,
                    )
                    or 0
                )

            if not feed.entries:
                break

            reached_older_records = False

            for entry in feed.entries:
                pub = ensure_utc(
                    dtparse(entry.published)
                )

                if pub > d1:
                    continue

                if pub < d0:
                    reached_older_records = True
                    continue

                title = " ".join(
                    entry.title.split()
                )
                arxiv_id = entry.id.rsplit(
                    "/",
                    1,
                )[-1]

                doi = normalize_doi(
                    getattr(entry, "arxiv_doi", "")
                )

                rows.append({
                    "search_id": sid,
                    "source": "arXiv",
                    "source_id": arxiv_id,
                    "title": title,
                    "authors": "; ".join(
                        author.name
                        for author in entry.authors
                    ),
                    "year": str(pub.year),
                    "doi": doi,
                    "pmid": "",
                    "url": entry.id,
                    "abstract": " ".join(
                        entry.summary.split()
                    ),
                    "categories": "; ".join(
                        tag["term"]
                        for tag in entry.tags
                    ),
                    "published": entry.published,
                    "updated": entry.updated,
                    "title_normalized": normalize_title(
                        title
                    ),
                })

            start += batch

            if reached_older_records or start >= total:
                break

            time.sleep(3.1)

        rows = rows[
            : cfg["max_records_per_query"]
        ]

        csv_path = (
            RAW
            / "arxiv"
            / f"{sid}.csv"
        )
        write_rows(csv_path, rows)

        append_log({
            "search_id": sid,
            "source": "arXiv",
            "search_date_utc": utc_now(),
            "query_mode": mode,
            "domain_group": domain,
            "query_exact": query,
            "date_from": cfg["date_from"],
            "date_until": cfg["date_until"],
            "results_reported": total or 0,
            "records_downloaded": len(rows),
            "raw_file": ";".join(raw_files),
            "csv_file": str(csv_path),
            "status": "OK",
            "notes": (
                "Atom API; publication date "
                "filtered locally in UTC; "
                "3.1-second pause"
            ),
        })

        print(
            sid,
            total,
            len(rows),
        )

        time.sleep(3.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=None,
    )
    args = parser.parse_args()

    run(load_config(args.config))