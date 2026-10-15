"""Durable study revisions, runs and jobs in PostgreSQL or local SQLite."""
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
import psycopg

from src.shared.database import warehouse_configured, connect_to_warehouse
from ..integrated.context import digest

logger = logging.getLogger(__name__)


class StoreError(RuntimeError):
    pass


class Conflict(ValueError):
    pass


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS planning_submissions (scope TEXT NOT NULL, request_key TEXT NOT NULL, input_hash TEXT NOT NULL, study_id TEXT NOT NULL, job_id TEXT NOT NULL, PRIMARY KEY(scope,request_key))",
    "CREATE TABLE IF NOT EXISTS planning_benchmarks (id TEXT PRIMARY KEY, signature TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, payload TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS planning_benchmarks_signature_idx ON planning_benchmarks(signature,created_at)",
    "CREATE TABLE IF NOT EXISTS planning_documents (id TEXT PRIMARY KEY, kind TEXT NOT NULL, study_id TEXT, created_at DOUBLE PRECISION NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS planning_jobs (id TEXT PRIMARY KEY, study_id TEXT NOT NULL, mode TEXT NOT NULL, idempotency_key TEXT NOT NULL, input_hash TEXT NOT NULL, status TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, heartbeat DOUBLE PRECISION, lease_id TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0, result_id TEXT, progress TEXT, error TEXT, UNIQUE(study_id,idempotency_key))",
    "CREATE INDEX IF NOT EXISTS planning_jobs_queue_idx ON planning_jobs(status,created_at)",
    "CREATE TABLE IF NOT EXISTS planning_job_owners (job_id TEXT PRIMARY KEY, lease_id TEXT NOT NULL, identity_json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS planning_job_attempts (lease_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, started_at DOUBLE PRECISION NOT NULL, ended_at DOUBLE PRECISION, status TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS planning_child_cache (cache_key TEXT PRIMARY KEY, result_id TEXT NOT NULL, result_hash TEXT NOT NULL, descriptor_json TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)",
    "CREATE TABLE IF NOT EXISTS planning_job_children (job_id TEXT NOT NULL, child_key TEXT NOT NULL, status TEXT NOT NULL, descriptor_json TEXT NOT NULL, result_id TEXT, error TEXT, updated_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(job_id,child_key))",
    "CREATE TABLE IF NOT EXISTS planning_child_locks (child_key TEXT PRIMARY KEY, job_id TEXT NOT NULL, lease_id TEXT NOT NULL)",
)


class Session:
    def __init__(self, connection, postgres):
        self.connection, self.postgres = connection, postgres

    def execute(self, sql, arguments=()):
        return self.connection.execute(sql.replace("?", "%s") if self.postgres else sql, arguments)


@contextmanager
def transaction():
    postgres = warehouse_configured() and not os.getenv("PLANNING_SQLITE_PATH")
    connection = None
    try:
        if postgres:
            connection = connect_to_warehouse()
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('planning_studies_schema'))")
        else:
            path = Path(os.getenv("PLANNING_SQLITE_PATH", str(Path(os.getenv("DATA_DIR", "data"))/"planning/studies.sqlite")))
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=10, isolation_level=None)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
        session = Session(connection, postgres)
        for statement in SCHEMA:
            session.execute(statement)
        yield session
        connection.commit()
    except (sqlite3.Error, psycopg.Error, OSError) as error:
        if connection:
            connection.rollback()
        logger.exception('Planning storage transaction failed (%s)', 'postgres' if postgres else 'sqlite')
        raise StoreError("Planning storage unavailable") from error
    except Exception:
        if connection:
            connection.rollback()
        raise
    finally:
        if connection:
            connection.close()


def _save(session, kind, payload, study_id=None):
    identifier, now = str(uuid4()), time.time()
    result = {**payload, "id": identifier, "created_at": now}
    if study_id:
        result["study_id"] = study_id
    session.execute("INSERT INTO planning_documents(id,kind,study_id,created_at,payload) VALUES(?,?,?,?,?)",
                    (identifier, kind, study_id, now, json.dumps(result, ensure_ascii=False, allow_nan=False)))
    return result


def save_study(inputs, context_hash, parent_id=None):
    with transaction() as session:
        if parent_id and session.execute("SELECT id FROM planning_documents WHERE id=? AND kind='study'", (parent_id,)).fetchone() is None:
            raise ValueError("Parent study revision not found")
        return _save(session, "study", {"inputs": inputs, "context_hash": context_hash, "parent_revision_id": parent_id})


def load_document(identifier, kind):
    with transaction() as session:
        row = session.execute("SELECT payload FROM planning_documents WHERE id=? AND kind=?", (str(identifier), kind)).fetchone()
        return json.loads(row[0]) if row else None


def start_study(inputs, context_hash, scope, mode, request_key):
    """Commit the frozen input and queued job together; retries reuse the same job."""
    signature = digest({'inputs': inputs, 'context_hash': context_hash, 'mode': mode})
    with transaction() as session:
        previous = session.execute(
            'SELECT input_hash,study_id,job_id FROM planning_submissions WHERE scope=? AND request_key=?',
            (scope, request_key)).fetchone()
        if previous:
            if previous[0] != signature:
                raise Conflict('Run request key was already used with different inputs')
            row = session.execute("SELECT payload FROM planning_documents WHERE id=? AND kind='study'", (previous[1],)).fetchone()
            if row is None:
                raise StoreError('Stored simulation input is unavailable')
            study, job_id = json.loads(row[0]), previous[2]
        else:
            study = _save(session, 'study', {'inputs': inputs, 'context_hash': context_hash, 'parent_revision_id': None})
            job_id = str(uuid4())
            session.execute("INSERT INTO planning_jobs(id,study_id,mode,idempotency_key,input_hash,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
                            (job_id, study['id'], mode, request_key, digest({'study': context_hash, 'mode': mode}), time.time()))
            session.execute('INSERT INTO planning_submissions(scope,request_key,input_hash,study_id,job_id) VALUES(?,?,?,?,?)',
                            (scope, request_key, signature, study['id'], job_id))
    job = get_job(job_id)
    if job is None:
        raise StoreError('Queued simulation is not visible in storage')
    return study, job


def latest_zoning_job(scope, source_prefix, scope_note):
    """Read completed history for the exact plan revision and spatial scope."""
    with transaction() as session:
        rows=session.execute('''SELECT j.id,d.payload FROM planning_submissions s
            JOIN planning_jobs j ON j.id=s.job_id
            JOIN planning_documents d ON d.id=j.study_id AND d.kind='study'
            WHERE s.scope=? AND j.status='succeeded'
            ORDER BY j.created_at DESC LIMIT 50''',(scope,)).fetchall()
    for identifier,payload in rows:
        note=json.loads(payload)['inputs'].get('source_note','')
        if note.startswith(source_prefix) and scope_note in note:
            return get_job(identifier)
    return None


def enqueue(study_id, mode, idempotency_key):
    with transaction() as session:
        row = session.execute("SELECT payload FROM planning_documents WHERE id=? AND kind='study'", (str(study_id),)).fetchone()
        if row is None:
            raise ValueError("Study revision not found")
        input_hash = digest({"study": json.loads(row[0])["context_hash"], "mode": mode})
        previous = session.execute("SELECT id,input_hash FROM planning_jobs WHERE study_id=? AND idempotency_key=?", (str(study_id), idempotency_key)).fetchone()
        if previous:
            if previous[1] != input_hash:
                raise Conflict("Idempotency key was already used for a different run request")
            identifier = previous[0]
        else:
            identifier = str(uuid4())
            session.execute("INSERT INTO planning_jobs(id,study_id,mode,idempotency_key,input_hash,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
                            (identifier, str(study_id), mode, idempotency_key, input_hash, time.time()))
    return get_job(identifier)


def get_job(identifier):
    with transaction() as session:
        row = session.execute("SELECT id,study_id,mode,status,created_at,heartbeat,cancel_requested,result_id,progress,error FROM planning_jobs WHERE id=?", (str(identifier),)).fetchone()
    if row is None:
        return None
    names = ("id", "study_id", "mode", "status", "created_at", "heartbeat", "cancel_requested", "result_id", "progress", "error")
    result = dict(zip(names, row))
    result["cancel_requested"] = bool(result["cancel_requested"])
    result["progress"] = json.loads(result["progress"]) if result["progress"] else None
    if result["progress"]:
        result["progress"] = {key: value for key, value in result["progress"].items() if key not in ("child_identity", "child_pid")}
    with transaction() as session:
        result["attempts"] = session.execute("SELECT COUNT(*) FROM planning_job_attempts WHERE job_id=?", (str(identifier),)).fetchone()[0]
        counts = session.execute("SELECT status,COUNT(*) FROM planning_job_children WHERE job_id=? GROUP BY status", (str(identifier),)).fetchall()
    result["child_counts"] = dict(counts)
    return result


def claim():
    from .identity import snapshot
    owner = snapshot(os.getpid())
    with transaction() as session:
        limit = int(os.getenv("PLANNING_MAX_RUNNING", "2"))
        if not 1 <= limit <= 8:
            raise ValueError("PLANNING_MAX_RUNNING must be between 1 and 8")
        if session.execute("SELECT COUNT(*) FROM planning_jobs WHERE status='running'").fetchone()[0] >= limit:
            return None
        suffix = " FOR UPDATE SKIP LOCKED" if session.postgres else ""
        row = session.execute("SELECT id,study_id,mode FROM planning_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1"+suffix).fetchone()
        if row is None:
            return None
        lease = str(uuid4())
        session.execute("UPDATE planning_jobs SET status='running',heartbeat=?,lease_id=? WHERE id=? AND status='queued'", (time.time(), lease, row[0]))
        session.execute("INSERT INTO planning_job_owners(job_id,lease_id,identity_json) VALUES(?,?,?) ON CONFLICT(job_id) DO UPDATE SET lease_id=excluded.lease_id,identity_json=excluded.identity_json", (row[0], lease, json.dumps(owner)))
        session.execute("INSERT INTO planning_job_attempts(lease_id,job_id,started_at,status) VALUES(?,?,?,'running')", (lease, row[0], time.time()))
    return {"id": row[0], "study_id": row[1], "mode": row[2], "lease_id": lease}


def heartbeat(job, progress):
    with transaction() as session:
        row = session.execute("SELECT status,cancel_requested,lease_id FROM planning_jobs WHERE id=?", (job["id"],)).fetchone()
        if row is None or row[0] != "running" or row[1] or row[2] != job["lease_id"]:
            return False
        session.execute("UPDATE planning_jobs SET heartbeat=?,progress=? WHERE id=?", (time.time(), json.dumps(progress, allow_nan=False), job["id"]))
    return True


def cancel(identifier):
    with transaction() as session:
        session.execute("UPDATE planning_jobs SET cancel_requested=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE id=? AND status IN ('queued','running')", (str(identifier),))
    return get_job(identifier)


def finish(job, result=None, error=None, cancelled=False):
    with transaction() as session:
        row = session.execute("SELECT status,cancel_requested,lease_id FROM planning_jobs WHERE id=?", (job["id"],)).fetchone()
        if row is None or row[0] != "running" or row[2] != job["lease_id"]:
            raise Conflict("Worker does not own the running job")
        if row[1] or cancelled:
            status, result_id = "cancelled", None
        elif error:
            completed = session.execute("SELECT COUNT(*) FROM planning_job_children WHERE job_id=? AND status='succeeded'", (job["id"],)).fetchone()[0]
            status, result_id = "partial" if completed else "failed", None
        elif result is not None:
            document = _save(session, "run", result, job["study_id"])
            status, result_id = "succeeded", document["id"]
            timing = result.get("runtime", {})
            if timing.get("benchmark_eligible"):
                sample = {"run_id": result_id, "job_id": job["id"], "compute_seconds": timing["compute_seconds"],
                          "profile": timing["benchmark_profile"], "scope": timing["scope"]}
                session.execute("INSERT INTO planning_benchmarks(id,signature,created_at,payload) VALUES(?,?,?,?)",
                                (str(uuid4()), timing["benchmark_profile"]["sha256"], time.time(), json.dumps(sample, allow_nan=False)))
        else:
            raise ValueError("Successful jobs require a result")
        session.execute("UPDATE planning_jobs SET status=?,result_id=?,error=?,heartbeat=? WHERE id=?", (status, result_id, error, time.time(), job["id"]))
        session.execute("UPDATE planning_job_attempts SET status=?,ended_at=? WHERE lease_id=?", (status, time.time(), job["lease_id"]))
        session.execute("UPDATE planning_job_children SET status=?,updated_at=? WHERE job_id=? AND status='running'", ("cancelled" if status == "cancelled" else "failed", time.time(), job["id"]))
        session.execute("DELETE FROM planning_child_locks WHERE job_id=? AND lease_id=?", (job["id"], job["lease_id"]))
    return get_job(job["id"])


def benchmark_samples(signature):
    with transaction() as session:
        rows = session.execute("SELECT payload FROM planning_benchmarks WHERE signature=? ORDER BY created_at DESC,id LIMIT 20", (signature,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def _owns(session, job):
    row = session.execute("SELECT status,cancel_requested,lease_id FROM planning_jobs WHERE id=?", (job["id"],)).fetchone()
    return row is not None and row[0] == "running" and not row[1] and row[2] == job["lease_id"]


def children(identifier):
    with transaction() as session:
        rows = session.execute("SELECT child_key,status,descriptor_json,result_id,error FROM planning_job_children WHERE job_id=? ORDER BY child_key", (str(identifier),)).fetchall()
    return [{"child_key": r[0], "status": r[1], "descriptor": json.loads(r[2]), "result_id": r[3], "error": r[4]} for r in rows]


def child_started(job, key, descriptor):
    with transaction() as session:
        if not _owns(session, job):
            return False
        session.execute("INSERT INTO planning_job_children(job_id,child_key,status,descriptor_json,updated_at) VALUES(?,?,'running',?,?) ON CONFLICT(job_id,child_key) DO UPDATE SET status='running',result_id=NULL,error=NULL,descriptor_json=excluded.descriptor_json,updated_at=excluded.updated_at", (job["id"], key, json.dumps(descriptor, allow_nan=False), time.time()))
    return True


def cached_child(key, descriptor):
    with transaction() as session:
        row = session.execute("SELECT result_id,result_hash,descriptor_json FROM planning_child_cache WHERE cache_key=?", (key,)).fetchone()
        if row is None or json.loads(row[2]) != descriptor:
            return None
        result = session.execute("SELECT payload FROM planning_documents WHERE id=? AND kind='child'", (row[0],)).fetchone()
        if result is None:
            return None
        document = json.loads(result[0])
        return document if digest(document["result"]) == row[1] else None


def child_completed(job, key, descriptor, result=None, cached_document=None):
    with transaction() as session:
        if not _owns(session, job):
            return False
        document = cached_document or _save(session, "child", {"descriptor": descriptor, "result": result}, job["study_id"])
        session.execute("INSERT INTO planning_child_cache(cache_key,result_id,result_hash,descriptor_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET result_id=excluded.result_id,result_hash=excluded.result_hash,descriptor_json=excluded.descriptor_json,updated_at=excluded.updated_at", (key, document["id"], digest(document["result"]), json.dumps(descriptor, allow_nan=False), time.time()))
        session.execute("UPDATE planning_job_children SET status='succeeded',result_id=?,updated_at=? WHERE job_id=? AND child_key=?", (document["id"], time.time(), job["id"], key))
    return True


def retry(identifier):
    with transaction() as session:
        row = session.execute("SELECT status FROM planning_jobs WHERE id=?", (str(identifier),)).fetchone()
        if row is None:
            raise KeyError("Job not found")
        if row[0] == "succeeded":
            raise Conflict("Completed immutable jobs cannot be retried; request a new run")
        if row[0] in ("failed", "partial", "cancelled"):
            session.execute("UPDATE planning_jobs SET status='queued',lease_id=NULL,cancel_requested=0,error=NULL,progress=NULL WHERE id=?", (str(identifier),))
    return get_job(identifier)


def recovery_candidates():
    with transaction() as session:
        rows = session.execute("SELECT j.id,j.lease_id,j.progress,o.identity_json FROM planning_jobs j LEFT JOIN planning_job_owners o ON j.id=o.job_id AND j.lease_id=o.lease_id WHERE j.status='running'").fetchall()
    return [{"id": r[0], "lease_id": r[1], "progress": json.loads(r[2]) if r[2] else {}, "owner": json.loads(r[3]) if r[3] else None} for r in rows]


def recover_stopped(job):
    # Process verification happens in recovery.py; fencing is checked again here.
    with transaction() as session:
        row = session.execute("SELECT status,lease_id,cancel_requested FROM planning_jobs WHERE id=?", (job["id"],)).fetchone()
        if row is None or row[0] != "running" or row[1] != job["lease_id"]:
            return False
        status = "cancelled" if row[2] else "queued"
        session.execute("UPDATE planning_jobs SET status=?,lease_id=NULL,error=NULL,progress=?,heartbeat=? WHERE id=?", (status, json.dumps({"module": "recovery", "reason": "Original local worker identity is verified stopped"}), time.time(), job["id"]))
        session.execute("UPDATE planning_job_attempts SET status='interrupted',ended_at=? WHERE lease_id=?", (time.time(), job["lease_id"]))
        session.execute("UPDATE planning_job_children SET status='failed',error='Worker interrupted before child completion',updated_at=? WHERE job_id=? AND status='running'", (time.time(), job["id"]))
        session.execute("DELETE FROM planning_child_locks WHERE job_id=? AND lease_id=?", (job["id"], job["lease_id"]))
    return True


def acquire_child_lock(job, key):
    with transaction() as session:
        if not _owns(session, job):
            return False
        row = session.execute("SELECT job_id,lease_id FROM planning_child_locks WHERE child_key=?", (key,)).fetchone()
        if row:
            if row == (job["id"], job["lease_id"]):
                return True
            owner = session.execute("SELECT status,lease_id FROM planning_jobs WHERE id=?", (row[0],)).fetchone()
            if owner and owner[0] == "running" and owner[1] == row[1]:
                return False
            session.execute("DELETE FROM planning_child_locks WHERE child_key=?", (key,))
        session.execute("INSERT INTO planning_child_locks(child_key,job_id,lease_id) VALUES(?,?,?)", (key, job["id"], job["lease_id"]))
    return True


def release_child_lock(job, key):
    with transaction() as session:
        session.execute("DELETE FROM planning_child_locks WHERE child_key=? AND job_id=? AND lease_id=?", (key, job["id"], job["lease_id"]))
