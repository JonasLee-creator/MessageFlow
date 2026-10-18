"""List/delete retired local evaluation artifacts; never touches raw sources or Git.

Default is read-only. --apply removes only recognized directories inside this
project's evaluation/results or the specifically identified second-study exports.
"""
import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def retired_reason(path):
    name = path.name
    if name.startswith(('real-replay-', 'adaptive-', 'v2-', 'v3-', 'integrated-plus-', 'checkpoint-smoke')):
        return 'retired experiment / second-study replay'
    if name == 'real-replay' or re.match(r'^(smoke(?:-|$)|planner-v[123]-)', name):
        return 'historical smoke experiment'
    cfg = read_json(path/'config.json')
    if cfg and (cfg.get('planner_version', 1) != 4 or cfg.get('optimizer_revision', 1) != 1 or cfg.get('online_version', 1) != 1):
        return 'retired planner configuration'
    return None


def candidates(root):
    result = []
    results = root/'evaluation/results'
    if results.is_dir():
        for path in sorted(results.iterdir()):
            if path.is_dir() and (reason := retired_reason(path)):
                result.append((path, reason, results))
    real = root/'real_data'
    if real.is_dir():
        for path in sorted(real.glob('converted-*')):
            report = read_json(path/'conversion_report.json')
            # Exact second-study fingerprint. No arbitrary future real export
            # is removed, and filled spreadsheets/observations are untouched.
            if (path.is_dir() and report.get('users') == 20 and
                report.get('observed_tasks') == 107 and report.get('replay_tasks') == 60 and
                report.get('execution_probability_assumption') == 1):
                result.append((path, 'second-study derived replay export', real))
    return result


def checked_target(path, allowed):
    """Resolve every descendant before recursive deletion; reject junction escapes."""
    allowed = allowed.resolve(strict=True)
    target = path.resolve(strict=True)
    if path.is_symlink() or target == allowed or not target.is_relative_to(allowed):
        raise ValueError(f'Unsafe cleanup target: {path}')
    for entry in path.rglob('*'):
        if entry.is_symlink() or not entry.resolve(strict=True).is_relative_to(target):
            raise ValueError(f'Linked/outside descendant: {entry}')
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    selected = candidates(ROOT)
    # Validate every target before making the first deletion.
    checked = [(checked_target(path, base), reason) for path, reason, base in selected]
    for target, reason in checked:
        print(f'{"DELETE" if args.apply else "WOULD DELETE"}: {target} ({reason})')
    if args.apply:
        for target, _ in checked:
            shutil.rmtree(target)
    print(f'{len(checked)} retired directories {"removed" if args.apply else "listed; no files changed"}.')


if __name__ == '__main__':
    main()
