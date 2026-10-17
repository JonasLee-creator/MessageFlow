"""Generate controlled V2 experiments; --run explicitly starts evaluation, never training."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SWITCHES=('enable_local_repair','enable_replan_cooldown','enable_low_gain_rejection')
CASES={
    'reference':(False,False,False),
    'local_only':(True,False,False),
    'cooldown_only':(False,True,False),
    'rejection_only':(False,False,True),
    'local_cooldown':(True,True,False),
    'combined':(True,True,True),
}
DEFAULT_CASES=('reference','local_only','local_cooldown','combined')
CONTROL_PARAMETERS=('local_max_affected_tasks','urgent_deadline_minutes',
                    'global_replan_cooldown_minutes','minimum_replan_gain')


def build_configs(base,defaults):
    result={}
    for name,values in CASES.items():
        config=dict(base)
        config.update({key:defaults[key] for key in CONTROL_PARAMETERS})
        config.update(dict(zip(SWITCHES,values)))
        config.update(planner_version=2,online_version=1,split='validation',
                      ablation_case=name,protocol_version='v2-control-ablation-1')
        result[name]=config
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New directory for configs and results')
    parser.add_argument('--checkpoint',type=Path)
    parser.add_argument('--model-config',type=Path,default=ROOT/'config/base.json')
    parser.add_argument('--dataset',type=Path,default=ROOT/'dataset')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--seeds',type=int,nargs='+',default=[11])
    parser.add_argument('--cases',choices=tuple(CASES),nargs='+',default=list(DEFAULT_CASES))
    parser.add_argument('--run',action='store_true',help='Explicitly run evaluation after preparing configs')
    args=parser.parse_args()
    if args.limit<=0:
        parser.error('--limit must be positive')
    if args.run and (args.checkpoint is None or not args.checkpoint.is_file()):
        parser.error('--run requires an existing --checkpoint; no training is performed')
    args.output=args.output.resolve()
    if args.checkpoint:
        args.checkpoint=args.checkpoint.resolve()
    args.dataset=args.dataset.resolve()
    args.model_config=args.model_config.resolve()
    base_path=ROOT/'evaluation/config_v2.json'
    base=json.loads(base_path.read_text(encoding='utf-8'))
    defaults=json.loads((ROOT/'evaluation/config_v3.json').read_text(encoding='utf-8'))
    configs=build_configs(base,defaults)
    args.output.mkdir(parents=True,exist_ok=False)
    folder=args.output/'configs'
    folder.mkdir()
    selected=list(dict.fromkeys(args.cases))
    for name in selected:
        (folder/f'{name}.json').write_text(json.dumps(configs[name],indent=2)+'\n',encoding='utf-8')
    manifest={'cases':selected,'seed_list':args.seeds,'limit':args.limit,
        'base_config_sha256':hashlib.sha256(base_path.read_bytes()).hexdigest(),
        'planner_family':'V2','online_version':1,'training':False,
        'status':'prepared','note':'All shared weights, scoring, checkpoint, users/scenarios and seeds held fixed.'}
    manifest_path=args.output/'experiment.json'
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Configs prepared: {folder}',flush=True)
    if not args.run:
        print('No evaluation started. Add --run and --checkpoint to execute in a new output directory.')
        return
    summaries=[]
    try:
        for name in selected:
            print(f'\n=== {name}: EVALUATION ONLY ===',flush=True)
            command=[sys.executable,str(ROOT/'evaluation/run_evaluation.py'),
                '--config',str(folder/f'{name}.json'),'--checkpoint',str(args.checkpoint),
                '--model-config',str(args.model_config),'--dataset',str(args.dataset),
                '--split','validation','--methods','drp_full','--output',str(args.output/name),
                '--limit',str(args.limit),'--seeds',*[str(s) for s in args.seeds]]
            process=subprocess.Popen(command,cwd=ROOT)
            try:
                code=process.wait()
                if code:
                    raise subprocess.CalledProcessError(code,command)
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise
            with (args.output/name/'summary.csv').open(encoding='utf-8-sig',newline='') as handle:
                summary=next(r for r in csv.DictReader(handle) if r['stress']=='all')
            summaries.append({'case':name,**dict(zip(SWITCHES,CASES[name])),**summary})
            with (args.output/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(summaries[0]))
                writer.writeheader()
                writer.writerows(summaries)
            columns=('weighted_ontime_rate','normalized_restricted_latency','cvar_deadline_loss',
                     'disruption_minutes','feasible')
            report='# V2 control ablations\n\nValidation subset; same checkpoint, seeds and old online updates.\n\n'
            report+='|Case|WOTCR ↑|Latency ↓|CVaR ↓|Movement ↓|Feasible ↑|\n|---|---:|---:|---:|---:|---:|\n'
            for row in summaries:
                values=['NA' if not row.get(k) else f'{float(row[k]):.4f}' for k in columns]
                report+='|'+row['case']+'|'+'|'.join(values)+'|\n'
            (args.output/'comparison.md').write_text(report,encoding='utf-8')
        manifest['status']='complete'
    except BaseException:
        manifest['status']='interrupted_or_failed'
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Comparison: {args.output / "comparison.md"}')


if __name__=='__main__':
    main()
