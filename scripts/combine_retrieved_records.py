from pathlib import Path
import pandas as pd
from common import ROOT

def main():
    paths=[p for p in (ROOT/'data_raw').rglob('*.csv')]
    if not paths: raise RuntimeError('No retrieved CSV files found.')
    frames=[]
    for p in paths:
        df=pd.read_csv(p,dtype=str).fillna(''); df['retrieval_file']=str(p.relative_to(ROOT)); frames.append(df)
    out=pd.concat(frames,ignore_index=True,sort=False)
    output=ROOT/'data_raw'/'all_retrieved_records_before_screening.csv'; out.to_csv(output,index=False)
    print(f'Saved {len(out)} source-query rows to {output}')
    print('Note: this file intentionally contains duplicates across sources and queries. Deduplicate only in the next pipeline stage.')
if __name__=='__main__': main()
