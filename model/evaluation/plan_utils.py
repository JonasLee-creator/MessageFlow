"""Shared physical-plan comparisons used by the V4 planner and replay."""


def changed_tasks(old, new, now, step):
    """Physical occupancy, independent of equivalent adjacent block encoding."""
    def footprint(blocks):
        result = {}
        for block in blocks:
            result.setdefault(block.task_id, set()).update(range(max(now, block.start), block.end, step))
        return result
    left, right = footprint(old), footprint(new)
    return {tid for tid in left.keys() | right.keys() if left.get(tid, set()) != right.get(tid, set())}
