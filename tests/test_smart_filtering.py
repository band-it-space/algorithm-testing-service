"""
Unit tests for SmartFilteringService.

Uses a real Redis instance (same as the app).
Run: python -m pytest tests/test_smart_filtering.py -v
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.smart_filtering_service import SmartFilteringService, _param_value_key


OPT_ID = "test_smart_filter_unit"


@pytest.fixture(autouse=True)
def cleanup():
    """Clean up Redis keys before and after each test."""
    SmartFilteringService.cleanup(OPT_ID)
    yield
    SmartFilteringService.cleanup(OPT_ID)


def _store_genomes(genomes, variable_params):
    """Helper to store genome-param mapping."""
    SmartFilteringService.store_genome_params(OPT_ID, genomes, variable_params)


def _make_genomes():
    """Create test genomes with 3 variable params × 3 values = 27 combos."""
    variable_params = ["param_A", "param_B", "param_C"]
    values_a = [0.1, 0.2, 0.3]
    values_b = [10, 20, 30]
    values_c = [1.0, 2.0, 3.0]

    genomes = []
    idx = 0
    for a in values_a:
        for b in values_b:
            for c in values_c:
                gid = f"G_{idx:03d}"
                genomes.append({
                    "genome_id": gid,
                    "parameters": {"param_A": a, "param_B": b, "param_C": c},
                })
                idx += 1

    return genomes, variable_params


class TestSmartFilteringService:

    def test_record_and_clear(self):
        """Record a genome with PR >= MIN_PAYOFF_RATIO → its param values are cleared."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        params = {"param_A": 0.1, "param_B": 10, "param_C": 1.0}
        SmartFilteringService.record_genome_result(OPT_ID, "G_001", 3.5, params)

        client = SmartFilteringService.get_redis_client()
        cleared_key = SmartFilteringService.CLEARED_KEY.format(opt_id=OPT_ID)

        for name, val in params.items():
            pv_key = _param_value_key(name, val)
            assert client.sismember(cleared_key, pv_key), f"{pv_key} should be cleared"

    def test_gradual_elimination(self):
        """MIN_OBSERVATIONS bad genomes for same param value → eliminated."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        # Record 2 bad genomes with param_C=3.0 (MIN_OBSERVATIONS=2)
        # But first clear param_A and param_B so they don't interfere
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_good", 5.0,
            {"param_A": 0.1, "param_B": 10, "param_C": 1.0}  # clears A=0.1, B=10
        )
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_good2", 4.0,
            {"param_A": 0.3, "param_B": 30, "param_C": 2.0}  # clears A=0.3, B=30
        )

        # Now record bad genomes with C=3.0
        params1 = {"param_A": 0.1, "param_B": 10, "param_C": 3.0}
        SmartFilteringService.record_genome_result(OPT_ID, "G_bad1", 1.5, params1)
        elim = SmartFilteringService.check_and_eliminate(OPT_ID, "G_bad1", 1.5, params1)
        assert len(elim) == 0, "Should not eliminate yet (only 1 observation)"

        params2 = {"param_A": 0.3, "param_B": 30, "param_C": 3.0}
        SmartFilteringService.record_genome_result(OPT_ID, "G_bad2", 1.0, params2)
        elim = SmartFilteringService.check_and_eliminate(OPT_ID, "G_bad2", 1.0, params2)

        assert len(elim) == 1, f"Should eliminate 1 param, got {elim}"
        assert elim[0][0] == "param_C"
        assert round(elim[0][1], 6) == 3.0

    def test_cleared_param_not_eliminated(self):
        """A cleared param is never eliminated even if later bad observations appear."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        # Clear param_A=0.1 with a good genome
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_good", 5.0,
            {"param_A": 0.1, "param_B": 10, "param_C": 1.0}
        )

        # Record bad genomes with param_A=0.1
        for i in range(3):
            params = {"param_A": 0.1, "param_B": 20, "param_C": 2.0}
            SmartFilteringService.record_genome_result(OPT_ID, f"G_bad{i}", 0.5, params)
            elim = SmartFilteringService.check_and_eliminate(OPT_ID, f"G_bad{i}", 0.5, params)
            # param_A=0.1 is cleared, should not be eliminated
            for e_param, e_val in elim:
                assert e_param != "param_A" or round(e_val, 6) != 0.1, \
                    "Cleared param_A=0.1 should not be eliminated"

    def test_out_payoff_ratio_instant_kill(self):
        """PR < OUT_PAYOFF_RATIO with exactly 1 non-cleared param → instant elimination."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        # Clear param_A=0.1 and param_B=10
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_good", 5.0,
            {"param_A": 0.1, "param_B": 10, "param_C": 1.0}
        )

        # Now a genome with PR < OUT_PAYOFF_RATIO (1.0) — only param_C=3.0 is non-cleared
        params = {"param_A": 0.1, "param_B": 10, "param_C": 3.0}
        SmartFilteringService.record_genome_result(OPT_ID, "G_terrible", 0.3, params)
        elim = SmartFilteringService.check_and_eliminate(OPT_ID, "G_terrible", 0.3, params)

        assert len(elim) == 1
        assert elim[0][0] == "param_C"
        assert round(elim[0][1], 6) == 3.0

    def test_out_payoff_ratio_multiple_non_cleared(self):
        """PR < OUT_PAYOFF_RATIO but 2+ non-cleared params → no instant elimination."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        # Only clear param_A=0.1
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_good", 5.0,
            {"param_A": 0.1, "param_B": 10, "param_C": 1.0}
        )

        # param_B=20 and param_C=3.0 are both non-cleared
        params = {"param_A": 0.1, "param_B": 20, "param_C": 3.0}
        SmartFilteringService.record_genome_result(OPT_ID, "G_terrible", 0.3, params)
        elim = SmartFilteringService.check_and_eliminate(OPT_ID, "G_terrible", 0.3, params)

        # Should NOT instantly eliminate (2 non-cleared params)
        assert len(elim) == 0

    def test_skip_list_populated(self):
        """After elimination, all genomes with the toxic param are in skip list."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        # Clear everything except param_C=3.0
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_g1", 5.0,
            {"param_A": 0.1, "param_B": 10, "param_C": 1.0}
        )
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_g2", 5.0,
            {"param_A": 0.2, "param_B": 20, "param_C": 2.0}
        )
        SmartFilteringService.record_genome_result(
            OPT_ID, "G_g3", 5.0,
            {"param_A": 0.3, "param_B": 30, "param_C": 1.0}
        )

        # Instant-kill param_C=3.0
        params = {"param_A": 0.1, "param_B": 10, "param_C": 3.0}
        SmartFilteringService.record_genome_result(OPT_ID, "G_bad", 0.3, params)
        SmartFilteringService.check_and_eliminate(OPT_ID, "G_bad", 0.3, params)

        # All genomes with param_C=3.0 should be in skip list
        genome_params = SmartFilteringService._get_genome_params(OPT_ID)
        for gid, gp in genome_params.items():
            if gid == "G_000":
                continue
            if round(float(gp.get("param_C", -1)), 6) == 3.0:
                assert SmartFilteringService.is_genome_skipped(OPT_ID, gid), \
                    f"{gid} with param_C=3.0 should be skipped"

    def test_skip_incremented_idempotent(self):
        """mark_skip_incremented returns True first time, False second time."""
        first = SmartFilteringService.mark_skip_incremented(OPT_ID, "G_test")
        assert first is True

        second = SmartFilteringService.mark_skip_incremented(OPT_ID, "G_test")
        assert second is False

    def test_base_genome_not_skipped(self):
        """G_000 should never be in skip list even if its params are toxic."""
        genomes = [
            {"genome_id": "G_000", "parameters": {"param_A": 0.1}},
            {"genome_id": "G_001", "parameters": {"param_A": 0.1}},
            {"genome_id": "G_002", "parameters": {"param_A": 0.2}},
        ]
        _store_genomes(genomes, ["param_A"])

        # Eliminate param_A=0.1
        SmartFilteringService.record_genome_result(OPT_ID, "G_x1", 0.5, {"param_A": 0.1})
        SmartFilteringService.record_genome_result(OPT_ID, "G_x2", 0.5, {"param_A": 0.1})
        SmartFilteringService.check_and_eliminate(OPT_ID, "G_x2", 0.5, {"param_A": 0.1})

        assert not SmartFilteringService.is_genome_skipped(OPT_ID, "G_000"), \
            "G_000 (BASE) should never be skipped"

    def test_filtering_summary(self):
        """get_filtering_summary returns correct structure."""
        genomes, vp = _make_genomes()
        _store_genomes(genomes, vp)

        summary = SmartFilteringService.get_filtering_summary(OPT_ID)
        assert summary["enabled"] is True
        assert summary["genomes_skipped"] == 0
        assert summary["eliminated_params"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
