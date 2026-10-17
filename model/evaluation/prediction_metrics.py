"""Dependency-free prediction diagnostics, preserving ties and missing labels."""
from __future__ import annotations
import math
from statistics import NormalDist
from .metrics import mean


def binary_metrics(probabilities,labels,bins=10):
    rows = [(max(1e-7,min(1-1e-7,float(p))),int(y)) for p,y in zip(probabilities,labels) if y is not None]
    if not rows:
        return {'n':0}
    ordered = sorted(rows,key=lambda x:x[0])
    positives = sum(y for _,y in rows)
    negatives = len(rows)-positives
    ranks,index = 0.,0
    while index<len(ordered):
        end=index+1
        while end<len(ordered) and ordered[end][0]==ordered[index][0]:
            end+=1
        ranks += sum(y for _,y in ordered[index:end])*((index+1+end)/2)
        index=end
    auc = (ranks-positives*(positives+1)/2)/(positives*negatives) if positives and negatives else None
    tp = sum(p>=.5 and y==1 for p,y in rows)
    fp = sum(p>=.5 and y==0 for p,y in rows)
    fn = sum(p<.5 and y==1 for p,y in rows)
    ece = 0.
    for b in range(bins):
        group = [(p,y) for p,y in rows if min(bins-1,int(p*bins))==b]
        if group:
            ece += len(group)/len(rows)*abs(mean(p for p,_ in group)-mean(y for _,y in group))
    risk_rows = sorted([(1-p,1-y) for p,y in rows],reverse=True)
    ap,found,count,index = 0.,0,0,0
    while index<len(risk_rows):
        end=index+1
        while end<len(risk_rows) and risk_rows[end][0]==risk_rows[index][0]:
            end+=1
        new=sum(y for _,y in risk_rows[index:end])
        found+=new
        count+=end-index
        if negatives:
            ap += new/negatives * found/count
        index=end
    return {'n':len(rows),'positive_rate':positives/len(rows),
        'bce':mean(-y*math.log(p)-(1-y)*math.log(1-p) for p,y in rows),
        'brier':mean((p-y)**2 for p,y in rows),'auroc':auc,
        'risk_average_precision':ap if negatives else None,
        'nonexecution_recall':sum(p<.5 and y==0 for p,y in rows)/negatives if negatives else None,
        'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.,'ece':ece}


def duration_metrics(parameters,targets):
    rows = [(float(mu),float(sigma),float(t)) for (mu,sigma),t in zip(parameters,targets) if t is not None and t>0]
    if not rows:
        return {'n':0}
    normal = NormalDist()
    q = lambda mu,sigma,p: math.exp(min(30,mu+sigma*normal.inv_cdf(p)))
    errors = sorted(abs(q(mu,s,.5)-t) for mu,s,t in rows)
    result = {'n':len(rows),'mae_minutes':mean(errors),
        'median_absolute_error':(errors[len(errors)//2]+errors[(len(errors)-1)//2])/2,
        'smape':mean(2*abs(q(mu,s,.5)-t)/(q(mu,s,.5)+t) for mu,s,t in rows),
        'nll':mean(math.log(t)+math.log(s)+.5*math.log(2*math.pi)+.5*((math.log(t)-mu)/s)**2 for mu,s,t in rows),
        'crps_minutes':mean(t*(2*normal.cdf((math.log(t)-mu)/s)-1)-2*math.exp(min(30,mu+s*s/2))*(
            normal.cdf((math.log(t)-mu)/s-s)+normal.cdf(s/math.sqrt(2))-1) for mu,s,t in rows),
        'interval90_width':mean(q(mu,s,.95)-q(mu,s,.05) for mu,s,t in rows)}
    for p in (.5,.8,.95):
        coverage = mean(t<=q(mu,s,p) for mu,s,t in rows)
        result[f'coverage_{p}'] = coverage
        result[f'coverage_error_{p}'] = abs(coverage-p)
    return result


def hypervolume3(points,reference):
    """Exact 3-D minimization hypervolume; reference fixed before testing."""
    points = [tuple(p) for p in points if all(p[i]<reference[i] for i in range(3))]
    xs = sorted({p[0] for p in points}|{reference[0]})
    volume = 0.
    for x,end in zip(xs,xs[1:]):
        active = [p for p in points if p[0]<=x]
        ys = sorted({p[1] for p in active}|{reference[1]})
        area = 0.
        for y,stop in zip(ys,ys[1:]):
            zs = [p[2] for p in active if p[1]<=y]
            if zs:
                area += (stop-y)*(reference[2]-min(zs))
        volume += (end-x)*area
    return volume
