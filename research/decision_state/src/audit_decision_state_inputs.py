#!/usr/bin/env python3
import os
import json, re
from pathlib import Path
import pandas as pd

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES=ROOT/'research/decision_state/results'
PROMPT=RES/'decision_state_prompt_cases.csv'
EVAL=RES/'decision_state_eval_cases.csv'

def main():
    prompt=pd.read_csv(PROMPT,low_memory=False)
    ev=pd.read_csv(EVAL,low_memory=False)
    forbidden=[]
    for c in prompt.columns:
        if re.search(r'future|^y_|evaluation_only|eval_complete|outcome',c,re.I): forbidden.append(c)
    assert not forbidden, forbidden
    assert 'case_id' in prompt.columns and len(prompt)==3000
    assert len(ev)==len(prompt) and ev.case_id.is_unique
    assert set(prompt.case_id)==set(ev.case_id)
    assert prompt.cutoff_date.isin(['2022-06-01','2022-07-01','2022-08-01']).all()
    assert prompt[['eth_return_1d','eth_return_7d','eth_volatility_7d','eth_drawdown_30d']].notna().all().all()
    result={'prompt_rows':len(prompt),'eval_rows':len(ev),'forbidden_prompt_columns':forbidden,'case_id_unique':bool(prompt.case_id.is_unique),'status':'PASS'}
    (RES/'decision_state_input_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
