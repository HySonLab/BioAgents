from __future__ import annotations
import argparse, time
import requests
from common import *
from http_helpers import request_with_retry
URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

logger = setup_logger('./logs/', 'search_europe_pmc')
def run(config):
    ensure_dirs(); session = requests.Session()
    for domain, query in europe_domain_queries(config):
        sid = stable_id("europepmc", domain, query); cursor = "*"; rows = []
        while cursor and len(rows) < int(config["max_records_per_query"]):
            data = request_with_retry(session, URL, params={"query": query, "format": "json", "resultType": "core", "pageSize": 1000, "cursorMark": cursor, "synonym": "false"}).json()
            items = data.get("resultList", {}).get("result", [])
            for item in items:
                keywords = item.get("keywordList", {}).get("keyword", [])
                if isinstance(keywords, str): keywords = [keywords]
                title = clean(item.get("title"))
                row = {"search_id": sid, "query_mode": "explicit_agents", "query_domain": domain, "source": "Europe PMC", "source_id": clean(item.get("id")), "title": title, "authors": clean(item.get("authorString")), "year": clean(item.get("pubYear")), "doi": norm_doi(item.get("doi")), "pmid": clean(item.get("pmid")), "pmcid": clean(item.get("pmcid")), "arxiv_id": "", "url": "", "abstract": clean(item.get("abstractText")), "keywords": "; ".join(map(clean, keywords)), "publication_type": "article", "venue": clean(item.get("journalTitle")), "title_normalized": norm_text(title)}
                row.update(validate_for_query_domain(row, config, domain)); rows.append(row)
            next_cursor = data.get("nextCursorMark")
            if not items or not next_cursor or next_cursor == cursor: break
            cursor = next_cursor; time.sleep(20)
        rows = rows[:int(config["max_records_per_query"])]
        write_rows(RAW / "europe_pmc" / f"{domain}.csv", [x for x in rows if x["search_logic_keep"]])
        write_rows(RAW / "europe_pmc" / f"{domain}_rejected.csv", [x for x in rows if not x["search_logic_keep"]])
        
        
        keep, rejected = sum(x["search_logic_keep"] for x in rows), sum(not x["search_logic_keep"] for x in rows)
        logger.info(f"{domain} kept {keep}, rejected {rejected}")

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default=None); args = parser.parse_args(); run(load_config(args.config))
if __name__ == "__main__": main()
