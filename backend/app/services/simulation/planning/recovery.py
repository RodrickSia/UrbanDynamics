"""Recover only after authoritative local process identity checks."""
from . import store, identity
from .cache import artifact_root


def recover():
    report = []
    for job in store.recovery_candidates():
        status = identity.state(job["owner"])
        if status != "stopped":
            report.append({"job_id": job["id"], "action": "kept", "owner_state": status})
            continue
        child = job["progress"].get("child_identity")
        if child and child.get("parent_pid") != job["owner"]["pid"]:
            report.append({"job_id": job["id"], "action": "kept", "reason": "Child was not recorded as belonging to the original worker"})
            continue
        if job["progress"].get("child_pid") and not child:
            report.append({"job_id": job["id"], "action": "kept", "reason": "Child identity cannot be verified"})
            continue
        if child and not identity.stop_orphan(child, artifact_root()):
            report.append({"job_id": job["id"], "action": "kept", "reason": "Owned child could not be safely stopped"})
            continue
        action = "recovered" if store.recover_stopped(job) else "changed_by_another_worker"
        report.append({"job_id": job["id"], "action": action, "owner_state": status})
    return report
