from __future__ import annotations
import argparse, time, requests
from common import *

URL='https://api.crossref.org/works'

def run(cfg):
    ensure_dirs(); s=requests.Session(); s.headers['User-Agent']=f"FEV-evidence-map/1.0 (mailto:{cfg['crossref_mailto']})"
    for mode,domain,query in build_concept_queries(cfg):
        sid=stable_search_id('crossref',mode,domain,query); cursor='*'; rows=[]; total=0; page=0; raw_files=[]
        while cursor and len(rows)<cfg['max_records_per_query']:
            params={"query.bibliographic":query,"filter":f"from-pub-date:{cfg['date_from']},until-pub-date:{cfg['date_until']}","rows":1000,"cursor":cursor,"mailto":cfg['crossref_mailto'],"select":"DOI,title,author,published,created,URL,abstract,type,container-title"}
            r=s.get(URL,params=params,timeout=120); r.raise_for_status(); data=r.json(); page+=1
            msg=data['message']; total=int(msg.get('total-results',0)); raw=RAW/'crossref'/f'{sid}_{page:04d}.json'; save_json(raw,data); raw_files.append(str(raw))
            items=msg.get('items',[])
            for x in items:
                title=(x.get('title') or [''])[0]; authors=[]
                for a in x.get('author',[]): authors.append(' '.join(filter(None,[a.get('given'),a.get('family')])))
                parts=(x.get('published') or {}).get('date-parts',[[None]])[0]; year=str(parts[0] or '')
                rows.append({"search_id":sid,"source":"Crossref","source_id":normalize_doi(x.get('DOI','')),"title":title,"authors":'; '.join(authors),"year":year,"doi":normalize_doi(x.get('DOI','')),"pmid":"","url":x.get('URL',''),"abstract":x.get('abstract',''),"publication_type":x.get('type',''),"venue":(x.get('container-title') or [''])[0],"title_normalized":normalize_title(title)})
            nxt=msg.get('next-cursor')
            if not items or not nxt or nxt==cursor: break
            cursor=nxt; time.sleep(1.0)
        rows=rows[:cfg['max_records_per_query']]
        csvp=RAW/'crossref'/f'{sid}.csv'; write_rows(csvp,rows)
        append_log({"search_id":sid,"source":"Crossref","search_date_utc":utc_now(),"query_mode":mode,"domain_group":domain,"query_exact":query,"date_from":cfg['date_from'],"date_until":cfg['date_until'],"results_reported":total,"records_downloaded":len(rows),"raw_file":';'.join(raw_files),"csv_file":str(csvp),"status":"OK","notes":"REST API cursor pagination; bibliographic query"})
        print(sid,total,len(rows)); time.sleep(1.0)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=None); a=ap.parse_args(); run(load_config(a.config))
