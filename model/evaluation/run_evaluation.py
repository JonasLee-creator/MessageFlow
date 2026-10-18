"""Explicit entry point: python evaluation/run_evaluation.py --help."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'src')]

from evaluation.domain import load_scenarios, scenario_split
from evaluation.metrics import cvar, mean, paired_bootstrap, paired_tail_bootstrap
from evaluation.planners import METHODS
from evaluation.predictor import Predictor
from evaluation.replay import replay


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def write_csv(path,rows):
    if rows:
        with path.open('w',encoding='utf-8-sig',newline='') as handle:
            writer = csv.DictWriter(handle,fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
            writer.writeheader()
            writer.writerows(rows)


def summarize(rows,alpha):
    result = []
    for method in sorted({r['method'] for r in rows}):
        for stress in ['all']+sorted({r['stress'] for r in rows}):
            subset = [r for r in rows if r['method']==method and (stress=='all' or r['stress']==stress)]
            if not subset:
                continue
            record = {'method':method,'stress':stress,'runs':len(subset),'scenarios':len({r['scenario_id'] for r in subset})}
            for metric in rows[0]:
                values = [r[metric] for r in subset if isinstance(r.get(metric),(int,float)) and metric!='seed']
                if values:
                    record[metric] = mean(values)
            record['cvar_deadline_loss'] = cvar([r['deadline_loss'] for r in subset],alpha)
            result.append(record)
    # Macro-average stress groups separately; do not silently change the overall mixture.
    for method in sorted({r['method'] for r in rows}):
        groups = [r for r in result if r['method']==method and r['stress']!='all']
        macro = {'method':method,'stress':'macro_stress'}
        for key in groups[0]:
            values = [g[key] for g in groups if isinstance(g.get(key),(int,float))]
            if values:
                macro[key] = mean(values)
        result.append(macro)
    return result


def main():
    parser = argparse.ArgumentParser(description='Paired causal scheduling simulation; never trains models.')
    parser.add_argument('--dataset',type=Path,default=ROOT/'dataset')
    parser.add_argument('--config',type=Path,default=ROOT/'evaluation/config_integrated.json')
    parser.add_argument('--checkpoint',type=Path)
    parser.add_argument('--model-config',type=Path,default=ROOT/'config/base.json')
    parser.add_argument('--output',type=Path,required=True,help='Must not exist: prevents overwriting experiments')
    parser.add_argument('--limit',type=int,help='Smoke/debug only; marks report non-final')
    parser.add_argument('--split',choices=('train','validation','test','all'))
    parser.add_argument('--seeds',type=int,nargs='+')
    parser.add_argument('--methods',choices=METHODS,nargs='+')
    parser.add_argument('--save-traces',action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    switches=('enable_local_repair','enable_replan_cooldown','enable_low_gain_rejection')
    if any(k in config and not isinstance(config[k],bool) for k in switches):
        parser.error('planner switches must be JSON booleans')
    if any(config.get(k,False) for k in switches):
        parser.error('retired experimental switches are not supported in the V4 release')
    if config.get('planner_version')!=4 or config.get('optimizer_revision',1)!=1 or config.get('online_version',1)!=1:
        parser.error('use the V4 main configuration: config_integrated.json')
    for key in ('split','seeds','methods'):
        if getattr(args,key) is not None:
            config[key] = getattr(args,key)
    if args.limit is not None and args.limit<=0:
        parser.error('--limit must be positive')
    if config['slot_minutes']<=0 or 1440%config['slot_minutes'] or config['planning_samples']<1:
        parser.error('invalid slot_minutes/planning_samples')
    if config['bootstrap_samples']<1 or not 0<config['cvar_alpha']<1:
        parser.error('invalid bootstrap_samples/cvar_alpha')
    if not config['methods'] or any(m not in METHODS for m in config['methods']):
        parser.error('unknown/empty methods')
    if config.get('planner_version',1)==4:
        if config['planning_samples']<2 or not config['repair_scopes'] or any(n<1 for n in config['repair_scopes']):
            parser.error('integrated planner requires >=2 samples and positive repair scopes')
        for key in ('guard_mean_tolerance','guard_completion_tolerance','guard_tail_tolerance','guard_response_tolerance','guard_confidence_z'):
            if config[key]<0:
                parser.error(f'{key} must be nonnegative')
    predictor = Predictor(config,args.checkpoint,args.model_config)
    source = args.dataset/'scenario_instances.jsonl'
    scenarios = list(load_scenarios(source,config['split']))
    if args.limit:
        scenarios = scenarios[:args.limit]
    if not scenarios:
        parser.error('no matching scenarios')
    args.output.mkdir(parents=True,exist_ok=False)
    write_json(args.output/'config.json',config)
    rows = []
    with (args.output/'runs.jsonl').open('w',encoding='utf-8') as handle:
        for index,scenario in enumerate(scenarios):
            predictor.cache.clear()
            for seed in config['seeds']:
                for method in config['methods']:
                    row,trace = replay(scenario,method,seed,config,predictor)
                    rows.append(row)
                    handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                    handle.flush()
                    if args.save_traces:
                        folder = args.output/'traces'
                        folder.mkdir(exist_ok=True)
                        write_json(folder/f'{scenario.id}-{seed}-{method}.json',trace)
            print(f'{index+1}/{len(scenarios)} scenarios complete',flush=True)
    summary = summarize(rows,config['cvar_alpha'])
    write_csv(args.output/'summary.csv',summary)
    comparisons = []
    for baseline in config['methods']:
        if baseline=='drp_full' or 'drp_full' not in config['methods']:
            continue
        for metric in ('weighted_ontime_rate','normalized_restricted_latency','disruption_minutes','deadline_loss'):
            comparisons.append(paired_bootstrap(rows,baseline,'drp_full',metric,config['bootstrap_samples'],config['seed']))
        comparisons.append(paired_tail_bootstrap(rows,baseline,'drp_full',config['bootstrap_samples'],config['seed'],config['cvar_alpha']))
    write_json(args.output/'comparisons.json',comparisons)
    lifts = [paired_bootstrap(rows,'global_probability','personalized',metric,config['bootstrap_samples'],config['seed'])
             for metric in ('weighted_ontime_rate','normalized_restricted_latency','deadline_loss')]
    write_json(args.output/'personalization_lift.json',lifts)
    try:
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        status = subprocess.check_output(['git','status','--porcelain','--','model'],cwd=ROOT.parent,text=True)
    except (OSError,subprocess.CalledProcessError):
        commit,status = None,'unknown'
    code_files = list((ROOT/'evaluation').glob('*.py'))
    manifest = {'protocol':config['protocol_version'],'planner_version':config.get('planner_version',1),
        'online_version':config.get('online_version',1),
        'optimizer_revision':config.get('optimizer_revision',1),
        'replay_version':'constraint-audited-3','python':sys.version,'platform':platform.platform(),
        'git_commit':commit,'model_tree_dirty':bool(status),'dataset_sha256':sha(source),
        'checkpoint_sha256':sha(args.checkpoint) if args.checkpoint else None,
        'model_config_sha256':sha(args.model_config),
        'evaluation_code_sha256':{p.name:sha(p) for p in code_files},
        'predictor':'trained_checkpoint' if args.checkpoint else 'UNTRAINED_PRIOR_REFERENCE',
        'debug_run':args.limit is not None,'scenario_ids':[s.id for s in scenarios],
        'split_rule':'SHA256 scenario ID, train60/validation20/test20; independent of user-heldout predictor test',
        'limitations':[
            'Simulation results, not causal effects on real users.',
            'Fixed intervals lack known_at: assumed initially known; no invented class-change timestamps.',
            'No exact oracle, oracle regret, Pareto hypervolume, or validated recovery-area metric reported.',
            'DRP is a finite candidate CVaR heuristic; no distributional ambiguity set or optimality guarantee.',
            'Neural features use cold-start user state and bucket prototypes; beta updates personalize observed feedback.',
            'Scenario is statistical cluster, not an identifiable real user.',
            'Tail CVaR evaluated on deadline-loss across runs; planning tail loss additionally penalizes unfinished work.',
            'restricted_latency is observed min(completion, end)-release, not Kaplan-Meier RMST.',
            'Non-splittable work restarts after interruption; reported retained work excludes discarded progress.',
            'All policies share the same freeze constraint and CPU settings; latency is measured, not a hard timeout.'
            ,'double_skip adds a public-clock-independent simulator shock at relative minutes 120 and 150.'
            ,'predicted_cvar_reduction compares forecasts, not realized recovery benefit or causal improvement.'
        ]}
    conversion_path = args.dataset/'conversion_report.json'
    if conversion_path.exists():
        conversion = json.loads(conversion_path.read_text(encoding='utf-8'))
        manifest['real_data_conversion'] = conversion
        manifest['real_data_conversion_sha256'] = sha(conversion_path)
        if config['split'] == 'all':
            manifest['split_rule'] = 'All supplied external observation windows; no synthetic hash split.'
    write_json(args.output/'manifest.json',manifest)
    write_json(args.output/'metric_directions.json',{
        'weighted_ontime_rate':'higher','completion_rate':'higher','feasible':'higher',
        'deadline_loss':'lower','cvar_deadline_loss':'lower','normalized_restricted_latency':'lower',
        'restricted_latency_minutes':'lower','disruption_minutes':'lower',
        'censored_fraction':'lower','unfinished_minutes':'lower'})
    header = '|Method|WOTCR ↑|Restricted latency ↓|CVaR90 loss ↓|Movement minutes ↓|Feasible ↑|\n|---|---:|---:|---:|---:|---:|\n'
    def fmt(value):
        return 'NA' if value is None else f'{value:.4f}'
    for row in summary:
        if row['stress']=='all':
            header += '|'+row['method']+'|'+'|'.join(fmt(row.get(k)) for k in (
                'weighted_ontime_rate','normalized_restricted_latency','cvar_deadline_loss','disruption_minutes','feasible'))+'|\n'
    notices=[]
    if any(s.stress=='real_replay' for s in scenarios):
        notices.append('REAL-DATA-DRIVEN SIMULATION: measured task durations, assumed execution probabilities; not a real-user trial.')
        if conversion_path.exists() and conversion.get('excluded_from_replay'):
            notices.append('COMPLETED-TASK SUBSET ONLY: incomplete/cancelled or unknown-duration tasks excluded; selection bias applies.')
    if args.limit:
        notices.append('DEBUG SUBSET: limited scenarios; not a final evaluation.')
    if not args.checkpoint:
        notices.append('PRIOR ONLY: no trained checkpoint loaded.')
    else:
        notices.append('TRAINED CHECKPOINT LOADED.')
    (args.output/'report.md').write_text('# Scheduling evaluation\n\n'+
        '\n'.join(notices)+'\n\n'+
        header+'\nSee manifest.json for assumptions; comparisons.json uses scenario-cluster bootstrap.\n',encoding='utf-8')
    print(f'Results: {args.output}')


if __name__=='__main__':
    main()
