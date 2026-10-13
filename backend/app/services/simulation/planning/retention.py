"""Keep saved results indefinitely; collect old, unreferenced planning workdirs.

Deletion is opt-in for a root owned exclusively by this planning store. Holding
the store transaction prevents claim/retry while checking and collecting.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import time

from . import store
from .cache import artifact_root

PREFIXES = ("planning-network-", "planning-sumo-", "planning-swmm-")


def references(value):
    if isinstance(value, dict):
        if "artifact_id" in value and "files" in value:
            yield value["artifact_id"]
        for member in value.values():
            yield from references(member)
    elif isinstance(value, list):
        for member in value:
            yield from references(member)


def latest_write(directory):
    """Inspect descendants without traversing links, including NTFS junctions."""
    pending, latest = [directory], 0
    while pending:
        entry = pending.pop()
        if entry.is_symlink() or entry.is_junction():
            return None
        latest = max(latest, entry.stat().st_mtime)
        if entry.is_dir():
            pending.extend(entry.iterdir())
    return latest


def collect(*, apply=False, exclusive_root=False, min_age_days=7, now=None):
    if not math.isfinite(min_age_days) or min_age_days < 1:
        raise ValueError("Retention age must be finite and at least one day")
    if apply and not exclusive_root:
        raise ValueError("Deletion requires a root exclusive to this planning store")
    root = artifact_root()
    cutoff = (time.time() if now is None else now) - min_age_days * 86400
    report = {"root": str(root), "mode": "apply" if apply else "dry_run",
              "min_age_days": min_age_days, "policy": "retain_all_referenced_artifacts",
              "candidates": [], "deleted": [], "protected": [], "skipped": []}
    with store.transaction() as session:
        active = session.execute("SELECT COUNT(*) FROM planning_jobs WHERE status IN ('queued','running')").fetchone()[0]
        if active:
            raise store.Conflict("Retention requires no queued or running planning jobs")
        protected = set()
        # Runs, uncertainty cases and complete children for cache/partial retry
        # all retain their artifacts, even when no longer the newest run.
        for row in session.execute("SELECT payload FROM planning_documents").fetchall():
            for identifier in references(json.loads(row[0])):
                if not isinstance(identifier, str) or Path(identifier).name != identifier:
                    raise ValueError("Invalid stored artifact reference; cleanup aborted")
                protected.add(identifier)
        for directory in sorted(root.iterdir()) if root.is_dir() else []:
            if not directory.name.startswith(PREFIXES):
                continue
            # Never traverse a symlink/junction or cross the resolved root.
            if directory.is_symlink() or directory.is_junction() or directory.resolve().parent != root:
                report["skipped"].append({"id": directory.name, "reason": "linked_or_outside_root"})
                continue
            if not directory.is_dir():
                continue
            if directory.name in protected:
                report["protected"].append(directory.name)
                continue
            # A recently written descendant means the workdir is still recent.
            latest = latest_write(directory)
            if latest is None:
                report["skipped"].append({"id": directory.name, "reason": "linked_descendant"})
                continue
            if latest > cutoff:
                continue
            report["candidates"].append(directory.name)
            if apply:
                # Explicit absolute containment check immediately before delete.
                target = directory.resolve()
                if target.parent != root or target == root:
                    raise ValueError("Artifact deletion escaped its root")
                shutil.rmtree(target)
                report["deleted"].append(directory.name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--exclusive-planning-root", action="store_true",
                        help="Assert this root is used only by this planning store")
    parser.add_argument("--min-age-days", type=float, default=7)
    args = parser.parse_args()
    print(json.dumps(collect(apply=args.apply, exclusive_root=args.exclusive_planning_root,
                             min_age_days=args.min_age_days), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
