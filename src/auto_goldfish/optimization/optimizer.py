"""Hyperband optimizer for deck configuration.

Uses the Hyperband algorithm (Li et al., 2018) to efficiently identify
the best deck configurations from the full enumerated search space.
Multiple brackets of successive halving with different aggressiveness
levels hedge against the explore-exploit tradeoff, allocating more
simulation budget to promising configurations while cheaply eliminating
obvious underperformers.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from auto_goldfish.optimization.candidate_cards import CandidateCard
from auto_goldfish.optimization.deck_config import DeckConfig, apply_config, enumerate_configs


class DeckOptimizer:
    """Hyperband optimizer for deck configuration.

    Enumerates all valid configurations within the given bounds,
    then uses Hyperband (multi-bracket successive halving) to
    efficiently identify the top performers before a final
    full-accuracy evaluation pass.

    Hyperband runs multiple brackets of successive halving:
    - The most aggressive bracket starts all configs with few sims
      and eliminates aggressively
    - Less aggressive brackets start fewer configs with more sims
    - This hedges against the tradeoff between breadth and depth

    Args:
        goldfisher: Goldfisher instance (will be mutated during optimization).
        candidates: Dict of candidate_id -> CandidateCard to consider.
        swap_mode: If True, remove no-effect spells to maintain deck size.
        max_draw: Maximum number of draw candidates to add (0-2).
        max_ramp: Maximum number of ramp candidates to add (0-2).
        land_range: Land delta range (-land_range to +land_range).
        optimize_for: Target metric - "mean_mana" or "consistency".
        sims_per_eval: Max simulations per config during enumeration.
            Higher values give more accurate rankings but take longer.
    """

    ETA = 3  # halving rate (standard Hyperband default)
    MIN_SIMS = 20  # minimum useful simulation count per evaluation

    def __init__(
        self,
        goldfisher,
        candidates: Dict[str, CandidateCard],
        swap_mode: bool = False,
        max_draw: int = 2,
        max_ramp: int = 2,
        land_range: int = 2,
        optimize_for: str = "mean_mana",
        sims_per_eval: int = 500,
    ) -> None:
        self.goldfisher = goldfisher
        self.candidates = candidates
        self.swap_mode = swap_mode
        self.max_draw = max_draw
        self.max_ramp = max_ramp
        self.land_range = land_range
        self.optimize_for = optimize_for
        self.sims_per_eval = sims_per_eval

    def run(
        self,
        final_sims: int = 1000,
        final_top_k: int = 5,
        enum_progress: Optional[Callable[[int, int], None]] = None,
        eval_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[Tuple[DeckConfig, Any]]:
        """Run optimization and return ranked (config, result_dict) pairs.

        Phase 1 (Hyperband): Efficiently narrow the full config space down
        to the most promising candidates using multi-bracket successive halving.

        Phase 2 (Final evaluation): Re-evaluate top candidates with full
        simulation count for accurate final ranking.

        Args:
            final_sims: Simulations for final evaluation of top configs.
            final_top_k: Number of top configs to fully evaluate.
            enum_progress: Optional callable(current, total) for enumeration.
                Current/total are measured in total simulations run.
            eval_progress: Optional callable(current, total) for evaluation.

        Returns:
            List of (DeckConfig, result_dict) sorted best-first.
        """
        configs = enumerate_configs(
            self.candidates,
            max_draw=self.max_draw,
            max_ramp=self.max_ramp,
            land_range=self.land_range,
        )

        original_sims = self.goldfisher.sims

        # Phase 1: Hyperband selection
        top_configs = self._hyperband_select(configs, final_top_k, enum_progress)

        # Phase 2: Full evaluation of top configs
        self.goldfisher.sims = final_sims
        from auto_goldfish.metrics.reporter import result_to_dict

        results: list[tuple[DeckConfig, Any]] = []
        for j, config in enumerate(top_configs):
            apply_config(self.goldfisher, config, self.candidates, self.swap_mode)
            result = self.goldfisher.simulate()
            results.append((config, result_to_dict(result)))

            if eval_progress is not None:
                eval_progress(j + 1, len(top_configs))

        self.goldfisher.sims = original_sims

        # Sort final results by target metric
        results.sort(key=lambda r: self._extract_score_from_dict(r[1]), reverse=True)
        return results

    # -- Hyperband internals --

    def _hyperband_select(
        self,
        configs: List[DeckConfig],
        top_k: int,
        progress: Optional[Callable[[int, int], None]],
    ) -> List[DeckConfig]:
        """Select top-K configs using Hyperband multi-bracket successive halving."""
        eta = self.ETA
        R = self.sims_per_eval
        min_sims = max(self.MIN_SIMS, R // 10)

        # s_max determines number of brackets; capped so initial sims >= min_sims
        s_max = max(0, int(math.floor(
            math.log(max(R / min_sims, 1)) / math.log(eta)
        )))

        n_max = len(configs)

        # Degenerate case: fewer configs than requested
        if n_max <= top_k:
            return list(configs)

        # Pre-compute bracket plans for budget estimation
        brackets = self._plan_brackets(n_max, R, eta, s_max, min_sims, top_k)
        total_budget = sum(
            n_i * r_i for bracket in brackets for n_i, r_i in bracket
        )

        done = [0]  # mutable for closure
        original_sims = self.goldfisher.sims
        rng = random.Random(
            self.goldfisher.seed if self.goldfisher.seed is not None else 42
        )

        def report(sims: int) -> None:
            done[0] += sims
            if progress is not None:
                progress(done[0], total_budget)

        # config -> (best_score, sims_used_for_that_score)
        all_survivors: dict[DeckConfig, tuple[float, int]] = {}

        for s_idx, bracket_plan in enumerate(brackets):
            s = s_max - s_idx

            # Most aggressive bracket uses all configs;
            # less aggressive brackets sample a subset
            if s == s_max:
                bracket_configs = list(configs)
            else:
                bracket_n = min(
                    max(math.ceil(n_max / eta ** (s_max - s)), top_k),
                    n_max,
                )
                bracket_configs = rng.sample(configs, bracket_n)

            survivors = self._successive_halving(bracket_configs, bracket_plan, report)

            # Record survivors with their final-round sim count
            r_final = bracket_plan[-1][1]
            for cfg, score in survivors:
                prev = all_survivors.get(cfg)
                # Prefer scores from higher sim counts (more accurate)
                if prev is None or r_final > prev[1] or (
                    r_final == prev[1] and score > prev[0]
                ):
                    all_survivors[cfg] = (score, r_final)

        self.goldfisher.sims = original_sims

        # Rank by (sims_used desc, score desc) to prefer high-confidence estimates
        ranked = sorted(
            all_survivors.items(),
            key=lambda x: (x[1][1], x[1][0]),
            reverse=True,
        )
        return [cfg for cfg, _ in ranked[:top_k]]

    def _plan_brackets(
        self,
        n_max: int,
        R: int,
        eta: int,
        s_max: int,
        min_sims: int,
        top_k: int,
    ) -> list[list[tuple[int, int]]]:
        """Pre-compute (num_configs, sims_per_config) for each round of each bracket.

        Must exactly match the logic in _successive_halving so the budget
        estimate is accurate for progress reporting.
        """
        brackets: list[list[tuple[int, int]]] = []

        for s in range(s_max, -1, -1):
            if s == s_max:
                n = n_max
            else:
                n = min(max(math.ceil(n_max / eta ** (s_max - s)), top_k), n_max)

            r_0 = max(math.ceil(R / eta ** s), min_sims)
            rounds: list[tuple[int, int]] = []
            n_i = n

            for i in range(s + 1):
                r_i = min(round(r_0 * eta ** i), R)
                rounds.append((n_i, r_i))
                # Configs kept for next round (matches _successive_halving)
                n_i = max(int(n_i / eta), 1)

            brackets.append(rounds)

        return brackets

    def _successive_halving(
        self,
        configs: list[DeckConfig],
        plan: list[tuple[int, int]],
        report: Callable[[int], None],
    ) -> list[tuple[DeckConfig, float]]:
        """Run one bracket of successive halving.

        Args:
            configs: Starting configurations for this bracket.
            plan: List of (expected_n, sims_per_config) per round.
            report: Callback to report sims completed for progress tracking.

        Returns:
            List of (config, score) for the final survivors.
        """
        eta = self.ETA
        current = list(configs)

        for round_idx, (_expected_n, r_i) in enumerate(plan):
            self.goldfisher.sims = r_i

            scored: list[tuple[DeckConfig, float]] = []
            for config in current:
                score = self._evaluate(config)
                scored.append((config, score))
                report(r_i)

            scored.sort(key=lambda x: x[1], reverse=True)

            # Keep top 1/eta fraction for next round (or as final survivors)
            keep = max(int(len(scored) / eta), 1)
            if round_idx < len(plan) - 1:
                current = [cfg for cfg, _ in scored[:keep]]
            else:
                scored = scored[:keep]

        return scored

    # -- Scoring --

    def _evaluate(self, config: DeckConfig) -> float:
        """Run a quick simulation and return the target metric score."""
        apply_config(self.goldfisher, config, self.candidates, self.swap_mode)
        result = self.goldfisher.simulate()
        return self._extract_score(result)

    def _extract_score(self, result) -> float:
        """Extract the optimization target from a SimulationResult."""
        if self.optimize_for == "consistency":
            return result.consistency
        if self.optimize_for == "mean_mana_value":
            return result.mean_mana_value
        if self.optimize_for == "mean_mana_total":
            return result.mean_mana_total
        return result.mean_mana

    def _extract_score_from_dict(self, result_dict: dict) -> float:
        """Extract score from a result_to_dict output."""
        if self.optimize_for == "consistency":
            return result_dict.get("consistency", 0.0)
        if self.optimize_for == "mean_mana_value":
            return result_dict.get("mean_mana_value", 0.0)
        if self.optimize_for == "mean_mana_total":
            return result_dict.get("mean_mana_total", 0.0)
        return result_dict.get("mean_mana", 0.0)
