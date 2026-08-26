from __future__ import annotations
import argparse, time, xml.etree.ElementTree as ET
from pathlib import Path
import requests
from common import *

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def pubmed_query(generic, date_from, date_until):
    # Search title/abstract while allowing exact domain phrases.
    terms = re.findall(r'"[^"]+"|\bAND\b|\bOR\b|\(|\)|[^\s()]+', generic)
    out=[]
    for t in terms:
        if t in {"AND","OR","(",")"}: out.append(t)
        else: out.append(f"{t}[Title/Abstract]")
    dates = f'("{date_from.replace("-","/")}"[Date - Publication] : "{date_until.replace("-","/")}"[Date - Publication])'
    return " ".join(out) + " AND " + dates

def article_rows(xml_bytes, search_id):
    root = ET.fromstring(xml_bytes)
    rows=[]
    for art in root.findall('.//PubmedArticle'):
        med=art.find('MedlineCitation'); article=med.find('Article') if med is not None else None
        pmid=(med.findtext('PMID') if med is not None else '') or ''
        title=''.join(article.find('ArticleTitle').itertext()) if article is not None and article.find('ArticleTitle') is not None else ''
        abstract=' '.join(''.join(x.itertext()) for x in article.findall('Abstract/AbstractText')) if article is not None else ''
        authors=[]
        if article is not None:
            for a in article.findall('AuthorList/Author'):
                name=' '.join(filter(None,[a.findtext('ForeName'),a.findtext('LastName')]))
                if name: authors.append(name)
        doi=''
        for aid in art.findall('.//ArticleId'):
            if aid.attrib.get('IdType')=='doi': doi=aid.text or ''
        year=''
        if article is not None:
            year=article.findtext('Journal/JournalIssue/PubDate/Year') or article.findtext('Journal/JournalIssue/PubDate/MedlineDate') or ''
        rows.append({"search_id":search_id,"source":"PubMed","source_id":pmid,"title":title,"authors":"; ".join(authors),"year":year[:4],"doi":normalize_doi(doi),"pmid":pmid,"url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else '',"abstract":abstract,"title_normalized":normalize_title(title)})
    return rows

def run(cfg):
    ensure_dirs(); session=requests.Session()
    common={"tool":"FEV_evidence_map","email":cfg["contact_email"]}
    if cfg.get("ncbi_api_key"): common["api_key"]=cfg["ncbi_api_key"]
    pause=0.12 if cfg.get("ncbi_api_key") else 0.36
    for mode,domain,generic in build_concept_queries(cfg):
        query=pubmed_query(generic,cfg["date_from"],cfg["date_until"])
        sid=stable_search_id("pubmed",mode,domain,query)
        params={**common,"db":"pubmed","term":query,"retmode":"json","retmax":0,"usehistory":"y"}
        r=session.get(f"{BASE}/esearch.fcgi",params=params,timeout=90); r.raise_for_status(); meta=r.json()
        save_json(RAW/"pubmed"/f"{sid}_esearch.json",meta)
        result=meta["esearchresult"]; count=int(result["count"]); webenv=result.get("webenv",""); qk=result.get("querykey","")
        rows=[]; batch=200
        for start in range(0,min(count,cfg["max_records_per_query"]),batch):
            fp={**common,"db":"pubmed","query_key":qk,"WebEnv":webenv,"retstart":start,"retmax":batch,"retmode":"xml"}
            x=session.get(f"{BASE}/efetch.fcgi",params=fp,timeout=120); x.raise_for_status()
            raw=RAW/"pubmed"/f"{sid}_efetch_{start:06d}.xml"; raw.parent.mkdir(parents=True,exist_ok=True); raw.write_bytes(x.content)
            rows.extend(article_rows(x.content,sid)); time.sleep(pause)
        csvp=RAW/"pubmed"/f"{sid}.csv"; write_rows(csvp,rows)
        append_log({"search_id":sid,"source":"PubMed","search_date_utc":utc_now(),"query_mode":mode,"domain_group":domain,"query_exact":query,"date_from":cfg["date_from"],"date_until":cfg["date_until"],"results_reported":count,"records_downloaded":len(rows),"raw_file":str(RAW/"pubmed"),"csv_file":str(csvp),"status":"OK","notes":"NCBI ESearch + EFetch"})
        print(sid,count,len(rows)); time.sleep(pause)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=None); args=ap.parse_args(); run(load_config(args.config))
