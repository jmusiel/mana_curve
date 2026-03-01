"""Background simulation job manager.

Runs Goldfisher simulations in daemon threads. Uses a semaphore to serialize
simulations because Goldfisher relies on module-level globals
(``_active_decklist``, ``_active_deckdict``) that are not thread-safe.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mana_curve.decklist.loader import load_decklist
from mana_curve.engine.goldfisher import Goldfisher
from mana_curve.metrics.reporter import result_to_dict


@dataclass
class SimJob:
    job_id: str
    deck_name: str
    config: Dict[str, Any]
    status: str = "pending"  # pending | running | completed | failed
    progress: int = 0
    total: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class SimulationRunner:
    """Manages background simulation jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, SimJob] = {}
        self._lock = threading.Lock()
        # Serialize simulations to avoid goldfisher global conflicts
        self._semaphore = threading.Semaphore(1)

    def submit(self, deck_name: str, config: Dict[str, Any]) -> str:
        """Start a background simulation. Returns the job ID."""
        job_id = uuid.uuid4().hex[:12]
        min_lands = config.get("min_lands", 36)
        max_lands = config.get("max_lands", 39)
        total = max_lands - min_lands + 1

        job = SimJob(
            job_id=job_id,
            deck_name=deck_name,
            config=config,
            total=total,
        )

        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_simulation,
            args=(job,),
            daemon=True,
        )
        thread.start()
        return job_id

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the current status of a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                "job_id": job.job_id,
                "deck_name": job.deck_name,
                "status": job.status,
                "progress": job.progress,
                "total": job.total,
                "config": job.config,
                "results": job.results,
                "error": job.error,
            }

    def _run_simulation(self, job: SimJob) -> None:
        """Execute the simulation in a background thread."""
        self._semaphore.acquire()
        try:
            with self._lock:
                job.status = "running"

            deck_list = load_decklist(job.deck_name)

            goldfisher = Goldfisher(
                deck_list,
                turns=job.config.get("turns", 10),
                sims=job.config.get("sims", 1000),
                verbose=False,
                record_results=job.config.get("record_results", "quartile"),
                deck_name=job.deck_name,
            )

            min_lands = job.config.get("min_lands", goldfisher.land_count)
            max_lands = job.config.get("max_lands", goldfisher.land_count)

            for i in range(min_lands, max_lands + 1):
                goldfisher.set_lands(i, cuts=job.config.get("cuts", []))
                result = goldfisher.simulate()
                result_dict = result_to_dict(result)

                with self._lock:
                    job.results.append(result_dict)
                    job.progress = len(job.results)

            with self._lock:
                job.status = "completed"

        except Exception as e:
            with self._lock:
                job.status = "failed"
                job.error = str(e)
        finally:
            self._semaphore.release()
