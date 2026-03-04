"""Background simulation job manager.

Runs Goldfisher simulations in daemon threads. GameState is self-contained
(no module-level globals), so concurrent simulations are safe.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from auto_goldfish.decklist.loader import load_decklist
from auto_goldfish.effects.card_database import DEFAULT_REGISTRY
from auto_goldfish.effects.json_loader import build_overridden_registry
from auto_goldfish.engine.goldfisher import Goldfisher
from auto_goldfish.engine.mulligan import CurveAwareMulligan
from auto_goldfish.metrics.reporter import result_to_dict


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
        try:
            with self._lock:
                job.status = "running"

            deck_list = load_decklist(job.deck_name)

            mulligan_strategy = None
            if job.config.get("mulligan") == "curve_aware":
                mulligan_strategy = CurveAwareMulligan()

            # Build custom registry if overrides provided
            effect_overrides = job.config.get("effect_overrides", {})
            registry = None
            if effect_overrides:
                registry = build_overridden_registry(DEFAULT_REGISTRY, effect_overrides)

            goldfisher = Goldfisher(
                deck_list,
                turns=job.config.get("turns", 10),
                sims=job.config.get("sims", 1000),
                verbose=False,
                record_results=job.config.get("record_results", "quartile"),
                deck_name=job.deck_name,
                seed=job.config.get("seed"),
                workers=job.config.get("workers", 1),
                mulligan_strategy=mulligan_strategy,
                registry=registry,
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

            try:
                from auto_goldfish.db.persistence import persist_completed_job

                persist_completed_job(job)
            except Exception:
                logger.exception("Failed to persist simulation run to DB")

        except Exception as e:
            with self._lock:
                job.status = "failed"
                job.error = str(e)
