import logging
import time

from . import store
from .engine import run_screening
from .models import PlanningStudy
from .context import build_context

logger = logging.getLogger(__name__)


class Cancelled(RuntimeError):
    pass


def process_one():
    job = store.claim()
    if job is None:
        return None
    started = time.monotonic()
    def checkpoint(progress):
        if not store.heartbeat(job, progress):
            raise Cancelled("Cancellation requested")
    try:
        revision = store.load_document(job["study_id"], "study")
        if revision is None:
            raise ValueError("Stored study revision unavailable")
        study = PlanningStudy(**revision["inputs"])
        context = build_context(study)
        if context["sha256"] != revision["context_hash"]:
            raise ValueError("Study context was created under a different model/library; create a new revision")
        checkpoint({"module": "preflight", "done": 0})
        child_executor = None
        if job["mode"] == "native" or job["mode"] == "uncertainty" and study.uncertainty.engine == "native":
            from .cache import ChildExecutor
            child_executor = ChildExecutor(job, checkpoint)
        if job["mode"] == "uncertainty":
            from .uncertainty import run
            result = run(study, checkpoint, child_executor)
        elif len(study.projects) == 1:
            from ..integrated.engine import predict_shared_study
            result = predict_shared_study(study, job["mode"], checkpoint, child_executor, context)
        elif job["mode"] == "native":
            from .native import run_native
            result = run_native(study, checkpoint, child_executor)
        else:
            result = run_screening(study, checkpoint)
        from .benchmark import measurement
        result["runtime"] = measurement(study, context, job["mode"], time.monotonic()-started, child_executor)
        checkpoint({"module": "complete", "done": result["unique_states_evaluated"], "total": result["unique_states_evaluated"]})
        return store.finish(job, result=result)
    except Cancelled:
        return store.finish(job, cancelled=True)
    except Exception:
        logger.exception("Planning job %s failed", job["id"])
        return store.finish(job, error="Planning calculation failed; inspect the worker log using this job ID.")
