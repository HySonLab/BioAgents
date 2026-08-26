from __future__ import annotations
import argparse, time, requests
from common import *

URL="https://www.ebi.ac.uk/europepmc/webservices/rest/search"

def epmc_query(generic,date_from,date_until):
    return f"({generic}) AND FIRST_PDATE:[{date_from} TO {date_until}]"

def run(cfg):
    ensure_dirs(); s=requests.Session()
    for mode,domain,generic in build_concept_queries(cfg):
        query=epmc_query(generic,cfg['date_from'],cfg['date_until'])
        sid=stable_search_id('europepmc',mode,domain,query)
        cursor='*'; rows=[]; page=0; hit_count=0; raw_files=[]
        while cursor and len(rows)<cfg['max_records_per_query']:
            params={"query":query,"format":"json","resultType":"core","pageSize":1000,"cursorMark":cursor,"synonym":"true"}
            r=s.get(URL,params=params,timeout=120); r.raise_for_status(); data=r.json(); page+=1
            hit_count=int(data.get('hitCount',0)); raw=RAW/'europe_pmc'/f'{sid}_{page:04d}.json'; save_json(raw,data); raw_files.append(str(raw))
            results=data.get('resultList',{}).get('result',[])
            for x in results:
                title=x.get('title',''); rows.append({"search_id":sid,"source":"Europe PMC","source_id":x.get('id',''),"title":title,"authors":x.get('authorString',''),"year":x.get('pubYear',''),"doi":normalize_doi(x.get('doi','')),"pmid":x.get('pmid',''),"pmcid":x.get('pmcid',''),"url":x.get('fullTextUrlList',{}).get('fullTextUrl',[{}])[0].get('url','') if x.get('fullTextUrlList',{}).get('fullTextUrl') else '',"abstract":x.get('abstractText',''),"publication_type":x.get('pubType',''),"title_normalized":normalize_title(title)})
            nxt=data.get('nextCursorMark')
            if not results or not nxt or nxt==cursor: break
            cursor=nxt; time.sleep(0.2)
        rows=rows[:cfg['max_records_per_query']]
        csvp=RAW/'europe_pmc'/f'{sid}.csv'; write_rows(csvp,rows)
        append_log({"search_id":sid,"source":"Europe PMC","search_date_utc":utc_now(),"query_mode":mode,"domain_group":domain,"query_exact":query,"date_from":cfg['date_from'],"date_until":cfg['date_until'],"results_reported":hit_count,"records_downloaded":len(rows),"raw_file":';'.join(raw_files),"csv_file":str(csvp),"status":"OK","notes":"REST API core results; synonyms enabled"})
        print(sid,hit_count,len(rows))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=None); a=ap.parse_args(); run(load_config(a.config))
