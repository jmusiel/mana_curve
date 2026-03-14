"""Unit tests for the optimization module."""

import math

from auto_goldfish.optimization.candidate_cards import (
    ALL_CANDIDATES,
    DRAW_CANDIDATES,
    RAMP_CANDIDATES,
    CandidateCard,
    make_custom_candidate,
)
from auto_goldfish.optimization.deck_config import (
    DeckConfig,
    enumerate_configs,
)
from auto_goldfish.optimization.optimizer import DeckOptimizer


class TestCandidateCards:
    def test_draw_candidates_count(self):
        assert len(DRAW_CANDIDATES) == 5

    def test_ramp_candidates_count(self):
        assert len(RAMP_CANDIDATES) == 3

    def test_all_candidates_contains_all(self):
        assert len(ALL_CANDIDATES) == 8

    def test_candidate_to_card_dict(self):
        c = DRAW_CANDIDATES[0]  # 1 Mana Draw 1
        d = c.to_card_dict()
        assert d["name"] == "[Opt] 1 Mana Draw 1"
        assert d["cmc"] == 1
        assert d["types"] == ["Sorcery"]

    def test_candidate_registry_name(self):
        c = RAMP_CANDIDATES[0]
        assert c.registry_name == "[Opt] 2 Mana Ramp +1"

    def test_candidate_to_registry_override(self):
        c = RAMP_CANDIDATES[0]
        override = c.to_registry_override()
        assert override["ramp"] is True
        assert "categories" in override

    def test_make_custom_draw(self):
        c = make_custom_candidate("draw", 3, 2)
        assert c.cmc == 3
        assert c.card_type == "draw"
        assert "Custom" in c.label

    def test_make_custom_ramp(self):
        c = make_custom_candidate("ramp", 2, 1)
        assert c.cmc == 2
        assert c.card_type == "ramp"

    def test_default_enabled_flags(self):
        enabled = [c for c in DRAW_CANDIDATES if c.default_enabled]
        disabled = [c for c in DRAW_CANDIDATES if not c.default_enabled]
        assert len(enabled) == 4  # 1cmc_1, 2cmc_2, 4cmc_3, 3cmc_1pt
        assert len(disabled) == 1  # 2cmc_1


class TestDeckConfig:
    def test_base_config(self):
        cfg = DeckConfig()
        assert cfg.land_delta == 0
        assert cfg.added_cards == ()
        assert cfg.describe() == "Base deck (no changes)"

    def test_config_describe(self):
        cfg = DeckConfig(land_delta=1, added_cards=("draw_2cmc_2",))
        desc = cfg.describe()
        assert "+1 land" in desc
        assert "Draw2(mv2)" in desc

    def test_config_negative_land(self):
        cfg = DeckConfig(land_delta=-2)
        assert "-2 land" in cfg.describe()

    def test_config_hashable(self):
        c1 = DeckConfig(land_delta=1, added_cards=("draw_1cmc_1",))
        c2 = DeckConfig(land_delta=1, added_cards=("draw_1cmc_1",))
        assert c1 == c2
        assert hash(c1) == hash(c2)
        s = {c1, c2}
        assert len(s) == 1

    def test_draw_ramp_count(self):
        cfg = DeckConfig(added_cards=("draw_1cmc_1", "draw_2cmc_2", "ramp_2cmc_1"))
        assert cfg.draw_count == 2
        assert cfg.ramp_count == 1


class TestEnumerateConfigs:
    def test_no_candidates(self):
        configs = enumerate_configs({}, max_draw=2, max_ramp=2, land_range=2)
        # Only land deltas: -2, -1, 0, +1, +2
        assert len(configs) == 5
        land_deltas = {c.land_delta for c in configs}
        assert land_deltas == {-2, -1, 0, 1, 2}
        # All should have empty added_cards
        assert all(c.added_cards == () for c in configs)

    def test_one_draw_candidate(self):
        candidates = {"draw_2cmc_2": ALL_CANDIDATES["draw_2cmc_2"]}
        configs = enumerate_configs(candidates, max_draw=2, max_ramp=0, land_range=0)
        # land_range=0 -> 1 land option
        # draw combos: (), (d,), (d,d) = 3
        # ramp combos: () = 1
        assert len(configs) == 3
        card_counts = sorted(len(c.added_cards) for c in configs)
        assert card_counts == [0, 1, 2]

    def test_draw_and_ramp(self):
        candidates = {
            "draw_2cmc_2": ALL_CANDIDATES["draw_2cmc_2"],
            "ramp_2cmc_1": ALL_CANDIDATES["ramp_2cmc_1"],
        }
        configs = enumerate_configs(candidates, max_draw=1, max_ramp=1, land_range=1)
        # land: -1, 0, +1 = 3
        # draw: (), (d) = 2
        # ramp: (), (r) = 2
        assert len(configs) == 3 * 2 * 2  # 12

    def test_includes_base_config(self):
        candidates = {
            cid: c for cid, c in ALL_CANDIDATES.items() if c.default_enabled
        }
        configs = enumerate_configs(candidates, max_draw=2, max_ramp=2, land_range=2)
        assert DeckConfig() in configs

    def test_includes_multi_card_configs(self):
        candidates = {
            "draw_2cmc_2": ALL_CANDIDATES["draw_2cmc_2"],
            "ramp_2cmc_1": ALL_CANDIDATES["ramp_2cmc_1"],
        }
        configs = enumerate_configs(candidates, max_draw=2, max_ramp=2, land_range=0)
        max_cards = max(len(c.added_cards) for c in configs)
        assert max_cards == 4  # 2 draw + 2 ramp

    def test_respects_land_range(self):
        configs = enumerate_configs({}, max_draw=0, max_ramp=0, land_range=3)
        land_deltas = {c.land_delta for c in configs}
        assert land_deltas == {-3, -2, -1, 0, 1, 2, 3}

    def test_asymmetric_land_deltas(self):
        configs = enumerate_configs(
            {}, max_draw=0, max_ramp=0, land_delta_min=-1, land_delta_max=3,
        )
        land_deltas = {c.land_delta for c in configs}
        assert land_deltas == {-1, 0, 1, 2, 3}

    def test_land_delta_min_max_overrides_land_range(self):
        configs = enumerate_configs(
            {}, max_draw=0, max_ramp=0, land_range=5,
            land_delta_min=-2, land_delta_max=1,
        )
        land_deltas = {c.land_delta for c in configs}
        assert land_deltas == {-2, -1, 0, 1}

    def test_no_duplicates(self):
        candidates = {
            cid: c for cid, c in ALL_CANDIDATES.items() if c.default_enabled
        }
        configs = enumerate_configs(candidates, max_draw=2, max_ramp=2, land_range=2)
        assert len(configs) == len(set(configs))


class TestHyperbandPlanning:
    """Unit tests for Hyperband bracket planning logic."""

    def _make_optimizer(self, hyperband_max_sims: int) -> DeckOptimizer:
        """Create an optimizer with a mock goldfisher for planning tests."""

        class FakeGoldfisher:
            seed = 42
            sims = 100

        return DeckOptimizer(
            goldfisher=FakeGoldfisher(),
            candidates={},
            hyperband_max_sims=hyperband_max_sims,
        )

    def test_s_max_low_sims(self):
        """With low hyperband_max_sims, s_max should be 0 (flat eval)."""
        opt = self._make_optimizer(hyperband_max_sims=20)
        eta = opt.ETA
        R = opt.hyperband_max_sims
        min_sims = max(opt.HYPERBAND_MIN_SIMS, R // 10)
        s_max = max(0, int(math.floor(
            math.log(max(R / min_sims, 1)) / math.log(eta)
        )))
        assert s_max == 0

    def test_s_max_high_sims(self):
        """With hyperband_max_sims=200, should get multiple brackets."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        eta = opt.ETA
        R = opt.hyperband_max_sims
        min_sims = max(opt.HYPERBAND_MIN_SIMS, R // 10)
        s_max = max(0, int(math.floor(
            math.log(max(R / min_sims, 1)) / math.log(eta)
        )))
        assert s_max == 2  # floor(log_3(10)) = 2

    def test_plan_brackets_count(self):
        """Number of brackets equals s_max + 1."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        assert len(brackets) == 3  # s=2, s=1, s=0

    def test_plan_brackets_round_counts(self):
        """Bracket s should have s+1 rounds."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        # brackets[0] is s=2 (3 rounds), brackets[1] is s=1 (2 rounds), brackets[2] is s=0 (1 round)
        assert len(brackets[0]) == 3
        assert len(brackets[1]) == 2
        assert len(brackets[2]) == 1

    def test_plan_brackets_most_aggressive_uses_all_configs(self):
        """Most aggressive bracket (s=s_max) starts with all configs."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        assert brackets[0][0][0] == 450  # first round of s=2 bracket

    def test_plan_brackets_sims_increase_per_round(self):
        """Within a bracket, sims per config should increase each round."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        for bracket in brackets:
            sims = [r_i for _, r_i in bracket]
            assert sims == sorted(sims), f"Sims should increase: {sims}"

    def test_plan_brackets_configs_decrease_per_round(self):
        """Within a bracket, config count should decrease each round."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        for bracket in brackets:
            counts = [n_i for n_i, _ in bracket]
            assert counts == sorted(counts, reverse=True), (
                f"Config counts should decrease: {counts}"
            )

    def test_plan_brackets_final_sims_capped_at_R(self):
        """Final round of every bracket should have sims <= R."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        for bracket in brackets:
            final_sims = bracket[-1][1]
            assert final_sims <= 200

    def test_plan_brackets_single_bracket_for_low_sims(self):
        """Low hyperband_max_sims produces a single bracket (flat eval)."""
        opt = self._make_optimizer(hyperband_max_sims=50)
        brackets = opt._plan_brackets(
            n_max=100, R=50, eta=3, s_max=0, min_sims=20, top_k=5,
        )
        assert len(brackets) == 1
        assert len(brackets[0]) == 1  # single round
        assert brackets[0][0][0] == 100  # all configs

    def test_hyperband_budget_less_than_flat(self):
        """Hyperband total budget should be less than flat enumeration."""
        opt = self._make_optimizer(hyperband_max_sims=200)
        brackets = opt._plan_brackets(
            n_max=450, R=200, eta=3, s_max=2, min_sims=20, top_k=5,
        )
        hyperband_budget = sum(
            n_i * r_i for bracket in brackets for n_i, r_i in bracket
        )
        flat_budget = 450 * 200
        assert hyperband_budget < flat_budget
