from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
from common import load_config, ROOT

# SCRIPTS={"pubmed":"search_pubmed.py","europe_pmc":"search_europe_pmc.py","arxiv":"search_arxiv.py","crossref":"search_crossref.py"}
SCRIPTS={"arxiv":"search_arxiv.py"}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=str(ROOT/'config'/'search_config.json')); a=ap.parse_args()
    cfg=load_config(a.config)
    for source,script in SCRIPTS.items():
        if cfg['sources'].get(source,False):
            cmd=[sys.executable,str(ROOT/'scripts'/script),'--config',a.config]
            print('\nRUNNING',' '.join(cmd),flush=True); subprocess.run(cmd,check=True,cwd=ROOT)
    print('\nAll enabled searches completed. Raw responses and CSV exports are under data_raw/.')

if __name__=='__main__': main()
