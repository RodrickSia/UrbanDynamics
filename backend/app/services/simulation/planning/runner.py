"""Interruptible solver execution; terminate only the child owned by this run."""
import os
from pathlib import Path
import subprocess
import time
import psutil

from ..integrated.solvers import SolverUnavailable
from .identity import snapshot_tree, stop_orphan


def execute(command, directory, checkpoint=None, timeout=None):
    if timeout is None:
        timeout=float(os.getenv('PLANNING_SOLVER_TIMEOUT_SECONDS','120'))
        if not 1 <= timeout <= 900:
            raise ValueError('Configured solver timeout must be between 1 and 900 seconds')
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[4])+os.pathsep+environment.get("PYTHONPATH", "")
    started = time.monotonic()
    with (directory/"engine-out.log").open("a", encoding="utf-8") as stdout, (directory/"engine-error.log").open("a", encoding="utf-8") as stderr:
        try:
            process = subprocess.Popen(command, cwd=directory, env=environment, stdout=stdout, stderr=stderr)
        except OSError as error:
            raise SolverUnavailable("Solver executable unavailable") from error
        try:
            try:
                child_identity = snapshot_tree(process.pid)
            except psutil.NoSuchProcess:
                child_identity = None  # A fast child already exited; poll handles its return code.
            while process.poll() is None:
                try:
                    child_identity = snapshot_tree(process.pid)
                except psutil.NoSuchProcess:
                    break
                if checkpoint:
                    checkpoint({"module": "solver", "child_pid": process.pid, "child_identity": child_identity,
                                "elapsed_seconds": round(time.monotonic()-started, 1)})
                if time.monotonic()-started > timeout:
                    raise SolverUnavailable("Solver exceeded its time limit")
                try:
                    process.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    pass
            process.wait(timeout=5)
            if process.returncode:
                raise SolverUnavailable(f"Solver failed; inspect {directory.name}/engine-error.log")
        except BaseException:
            if process.poll() is None:
                if child_identity:
                    stop_orphan(child_identity, directory.parent)
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            raise
