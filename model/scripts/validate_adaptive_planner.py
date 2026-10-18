"""Select fixed adaptive thresholds on ORIGINAL synthetic validation only.

No test split or real dataset option. Prepares experiments by default; --run
starts evaluation. A frozen config is emitted only after every case completes.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.adaptive_planner import DEFAULTS


def configs(base):
    conservative = dict(base, **DEFAULTS)
    conservative.update(planner_version=5, optimizer_revision=1,
        protocol_version='adaptive-validation-1',
        adaptive_max_load=.25, adaptive_min_slack_minutes=240.)
    balanced = dict(conservative, adaptive_max_load=.40, adaptive_min_slack_minutes=180.)
    return {'reference':dict(base), 'conservative':conservative, 'balanced':balanced}


def select_case(rows):
    """Descriptive validation gate, NOT a significance test or test guarantee."""
    ref = rows['reference']
    eligible = ['reference']
    for name, row in rows.items():
        if name == 'reference':
            continue
        if (row['weighted_ontime_rate'] >= ref['weighted_ontime_rate']-1e-12 and
            row['cvar_deadline_loss'] <= ref['cvar_deadline_loss']+1e-12 and
            row['normalized_restricted_latency'] <= ref['normalized_restricted_latency']+1e-12 and
            row['feasible'] >= 1.-1e-12):
            eligible.append(name)
    # Strict on the three primary outcomes, then optimize response and movement.
    # Exact ties prefer original, so complexity alone is not rewarded.
    chosen = min(eligible, key=lambda name:(
        -rows[name]['weighted_ontime_rate'], rows[name]['cvar_deadline_loss'],
        rows[name]['normalized_restricted_latency'], rows[name]['disruption_minutes'],
        name != 'reference', name))
    return chosen, eligible


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True, help='New output directory')
    p.add_argument('--checkpoint', type=Path)
    p.add_argument('--limit', type=int, default=20, help='Original validation scenarios; 0=all')
    p.add_argument('--seeds', nargs='+', type=int, default=[11])
    p.add_argument('--run', action='store_true')
    args = p.parse_args()
    if args.limit < 0 or len(set(args.seeds)) != len(args.seeds):
        p.error('limit must be >=0 and seeds must be unique')
    if args.run and (args.checkpoint is None or not args.checkpoint.is_file()):
        p.error('--run requires an existing trained checkpoint')
    source = ROOT/'dataset/scenario_instances.jsonl'
    # This is deliberately not an arbitrary --dataset path. Stop on accidental
    # real-data substitution, including if files were copied into dataset/.
    raw = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(r.get('simulated') is False or r.get('stress_type')=='real_replay' or r.get('evaluation_type') for r in raw):
        p.error('only the original synthetic validation dataset is allowed')
    base = json.loads((ROOT/'evaluation/config_integrated.json').read_text(encoding='utf-8'))
    candidates = configs(base)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'configs').mkdir()
    for name, config in candidates.items():
        config.update(split='validation', methods=['drp_full'], seeds=args.seeds)
        (out/'configs'/f'{name}.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    manifest = dict(status='prepared', dataset_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest() if args.checkpoint else None,
        split='validation', limit=args.limit or None, seeds=args.seeds, cases=list(candidates),
        selection_rule='No loss of validation mean WOTCR, tail CVaR or response; feasibility=1; otherwise keep reference.',
        limitation='Selected on validation, not evidence of improvement on an independent test set.')
    def save_manifest():
        (out/'selection.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    save_manifest()
    if not args.run:
        print(f'Prepared only: {out}. Add --run --checkpoint to evaluate in a new directory.')
        return
    rows, runs = {}, {}
    try:
        for name in candidates:
            command = [sys.executable, str(ROOT/'evaluation/run_evaluation.py'),
                '--dataset', str(ROOT/'dataset'), '--config', str(out/'configs'/f'{name}.json'),
                '--checkpoint', str(args.checkpoint.resolve()), '--split', 'validation',
                '--methods', 'drp_full', '--seeds', *map(str, args.seeds), '--output', str(out/name)]
            if args.limit:
                command.extend(['--limit', str(args.limit)])
            print(f'Validation case: {name}', flush=True)
            process = subprocess.Popen(command, cwd=ROOT)
            try:
                code = process.wait()
                if code:
                    raise subprocess.CalledProcessError(code, command)
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise
            with (out/name/'summary.csv').open(encoding='utf-8-sig', newline='') as f:
                raw_row = next(r for r in csv.DictReader(f) if r['stress']=='all')
            keys = ('weighted_ontime_rate', 'cvar_deadline_loss', 'normalized_restricted_latency', 'disruption_minutes', 'feasible')
            rows[name] = {k:float(raw_row[k]) for k in keys}
            runs[name] = [json.loads(line) for line in (out/name/'runs.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            # Enforce exact pairing before allowing automatic validation selection.
            pairs = lambda values: {(r['scenario_id'], r['seed']) for r in values}
            if len(pairs(runs[name])) != len(runs[name]) or pairs(runs[name]) != pairs(runs['reference']):
                raise ValueError('non-paired validation records; selection aborted')
        chosen, eligible = select_case(rows)
        frozen = dict(candidates[chosen], selected_on='synthetic_validation', validation_dataset_sha256=manifest['dataset_sha256'])
        (out/'frozen_config.json').write_text(json.dumps(frozen, indent=2)+'\n', encoding='utf-8')
        manifest.update(status='complete', chosen_case=chosen, eligible_cases=eligible, metrics=rows)
        report = '# Adaptive planner validation selection\n\nValidation selection, not independent test evidence.\n\n'
        report += '|Case|WOTCR ↑|Latency ↓|CVaR ↓|Movement ↓|Feasible ↑|\n|---|---:|---:|---:|---:|---:|\n'
        for name, r in rows.items():
            report += '|'+name+'|'+'|'.join(f'{r[k]:.4f}' for k in ('weighted_ontime_rate','normalized_restricted_latency','cvar_deadline_loss','disruption_minutes','feasible'))+'|\n'
        report += f'\nSelected: {chosen}. Frozen config: frozen_config.json\n'
        (out/'comparison.md').write_text(report, encoding='utf-8')
        print(report)
    except BaseException:
        manifest['status'] = 'interrupted_or_failed'
        raise
    finally:
        save_manifest()


if __name__ == '__main__':
    main()
