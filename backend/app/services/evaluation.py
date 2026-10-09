"""Reproducible heuristic checks, not a claim of predictive accuracy."""
from copy import deepcopy
from app.core.risk_engine import risk_engine

def evaluate():
    clean={'criteria':[{'required':True,'status':'passed','evidence':'job 42 passed','assigned_to':'owner'}],'blockers':[],'approvals':[{'decision':'approved'}],'days_to_target':30}
    baseline=risk_engine.assess_readiness(clean)['risk_score'];rows=[]
    changes=[('critical blocker',{'severity':'critical','status':'open'}),('high blocker',{'severity':'high','status':'open'}),('medium blocker',{'severity':'medium','status':'open'})]
    for name,blocker in changes:
        sample=deepcopy(clean);sample['blockers']=[blocker];score=risk_engine.assess_readiness(sample)['risk_score']
        rows.append({'case':name,'baseline':baseline,'actual':score,'passed':score>=baseline})
    sample=deepcopy(clean);sample['criteria'][0]['status']='failed';score=risk_engine.assess_readiness(sample)['risk_score']
    rows.append({'case':'failed required criterion','actual':score,'passed':score>baseline})
    for text,expected in [('authentication vulnerability cve','security'),('latency throughput memory','performance'),('dns deployment kubernetes','infrastructure')]:
        actual=risk_engine.classify_blocker(text,text)['category'];rows.append({'case':text,'expected':expected,'actual':actual,'passed':actual==expected})
    return {'total':len(rows),'passed':sum(r['passed'] for r in rows),'cases':rows,'scope':'Small fixed regression corpus. Not trained ML, general NLP accuracy, or calibrated failure probability.'}

if __name__=='__main__':
    import json
    result=evaluate();print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed']==result['total'] else 1)
