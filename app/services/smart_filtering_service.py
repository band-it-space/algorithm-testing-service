"""
Smart Filtering Service — Redis-backed toxic parameter elimination.

Detects parameter values that consistently produce bad Payoff Ratios
and removes remaining genomes containing those values from the queue.

Two elimination paths:
1. Gradual: >= MIN_OBSERVATIONS all below MIN_PAYOFF_RATIO
2. Instant (process-of-elimination): PR < OUT_PAYOFF_RATIO with exactly 1 non-cleared param
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

from app.config.smart_filtering_config import (
    MIN_PAYOFF_RATIO,
    OUT_PAYOFF_RATIO,
    MIN_OBSERVATIONS,
)

logger = logging.getLogger(__name__)


def _param_value_key(param_name: str, param_value: Any) -> str:
    """Create a stable string key for a (param, value) pair."""
    return f"{param_name}:{round(float(param_value), 6)}"


class SmartFilteringService:
    """Redis-backed smart filtering for genome optimization."""

    # Redis key patterns
    GENOMES_KEY = "smart_filter:genomes:{opt_id}"
    STATS_KEY = "smart_filter:stats:{opt_id}"
    CLEARED_KEY = "smart_filter:cleared:{opt_id}"
    SKIP_LIST_KEY = "smart_filter:skip_list:{opt_id}"
    SKIP_INCR_KEY = "smart_filter:skip_incremented:{opt_id}"
    ELIMINATED_KEY = "smart_filter:eliminated:{opt_id}"

    @staticmethod
    def get_redis_client():
        from app.services.queue_service import QueueService
        return QueueService.get_redis_client()

    # --- Setup ---

    @classmethod
    def store_genome_params(
        cls,
        optimization_id: str,
        genomes: List[Dict[str, Any]],
        variable_param_names: List[str],
    ) -> None:
        """
        Called once during optimization creation.
        Stores {genome_id: {param: value, ...}} for all genomes (variable params only).
        """
        client = cls.get_redis_client()
        key = cls.GENOMES_KEY.format(opt_id=optimization_id)

        mapping = {}
        for genome in genomes:
            gid = genome.get("genome_id", genome.get("id"))
            params = genome.get("parameters", {})
            variable_params = {
                name: params[name]
                for name in variable_param_names
                if name in params
            }
            mapping[gid] = variable_params

        client.set(key, json.dumps(mapping))
        logger.info(
            f"Smart filter: stored {len(mapping)} genome param mappings "
            f"for optimization {optimization_id} "
            f"({len(variable_param_names)} variable params)"
        )

    @classmethod
    def _get_genome_params(cls, optimization_id: str) -> Dict[str, Dict[str, Any]]:
        """Load genome-params mapping from Redis."""
        client = cls.get_redis_client()
        key = cls.GENOMES_KEY.format(opt_id=optimization_id)
        raw = client.get(key)
        if raw is None:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    # --- Skip Check (called by algorithm worker) ---

    @classmethod
    def is_genome_skipped(cls, optimization_id: str, genome_id: str) -> bool:
        """O(1) check — SISMEMBER on skip_list SET."""
        client = cls.get_redis_client()
        key = cls.SKIP_LIST_KEY.format(opt_id=optimization_id)
        return bool(client.sismember(key, genome_id))

    @classmethod
    def mark_skip_incremented(cls, optimization_id: str, genome_id: str) -> bool:
        """
        Atomically mark genome as counter-incremented.
        Returns True if newly added (first call), False if already existed.
        """
        client = cls.get_redis_client()
        key = cls.SKIP_INCR_KEY.format(opt_id=optimization_id)
        return bool(client.sadd(key, genome_id))

    # --- Result Recording ---

    @classmethod
    def record_genome_result(
        cls,
        optimization_id: str,
        genome_id: str,
        avg_payoff_ratio: float,
        param_values: Dict[str, Any],
    ) -> None:
        """
        Record averaged Payoff Ratio for a completed genome.

        For each (param, value) in param_values:
            1. Append avg_payoff_ratio to stats hash
            2. If avg_payoff_ratio >= MIN_PAYOFF_RATIO → add to cleared SET
        """
        client = cls.get_redis_client()
        stats_key = cls.STATS_KEY.format(opt_id=optimization_id)
        cleared_key = cls.CLEARED_KEY.format(opt_id=optimization_id)

        for param_name, param_value in param_values.items():
            pv_key = _param_value_key(param_name, param_value)

            # Append observation to stats
            raw = client.hget(stats_key, pv_key)
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                observations = json.loads(raw)
            else:
                observations = []

            observations.append({
                "genome_id": genome_id,
                "avg_pr": round(avg_payoff_ratio, 4),
            })
            client.hset(stats_key, pv_key, json.dumps(observations))

            # Clear if good
            if avg_payoff_ratio >= MIN_PAYOFF_RATIO:
                client.sadd(cleared_key, pv_key)

    # --- Toxic Parameter Identification ---

    @classmethod
    def check_and_eliminate(
        cls,
        optimization_id: str,
        genome_id: str,
        avg_payoff_ratio: float,
        param_values: Dict[str, Any],
    ) -> List[Tuple[str, Any]]:
        """
        Check if any parameter value should be eliminated.

        Two paths:
        1. OUT_PAYOFF_RATIO instant kill (process-of-elimination)
        2. Gradual elimination (MIN_PAYOFF_RATIO + MIN_OBSERVATIONS)

        Returns list of eliminated (param_name, param_value) tuples.
        """
        client = cls.get_redis_client()
        cleared_key = cls.CLEARED_KEY.format(opt_id=optimization_id)
        stats_key = cls.STATS_KEY.format(opt_id=optimization_id)

        eliminated = []

        # Path 1: Instant kill via process-of-elimination
        if avg_payoff_ratio < OUT_PAYOFF_RATIO:
            non_cleared = []
            for param_name, param_value in param_values.items():
                pv_key = _param_value_key(param_name, param_value)
                if not client.sismember(cleared_key, pv_key):
                    non_cleared.append((param_name, param_value, pv_key))

            if len(non_cleared) == 1:
                param_name, param_value, pv_key = non_cleared[0]
                # Check not already eliminated
                elim_key = cls.ELIMINATED_KEY.format(opt_id=optimization_id)
                if not client.hexists(elim_key, pv_key):
                    evidence = {
                        "method": "process_of_elimination",
                        "trigger_genome": genome_id,
                        "avg_pr": round(avg_payoff_ratio, 4),
                    }
                    cls._eliminate_param_value(
                        optimization_id, param_name, param_value, evidence
                    )
                    eliminated.append((param_name, param_value))
                    return eliminated  # Done — only one elimination per call

        # Path 2: Gradual elimination
        # Check ALL param-values in stats (not just this genome's)
        all_stats_raw = client.hgetall(stats_key)
        candidates = []

        for pv_key_raw, obs_raw in all_stats_raw.items():
            pv_key = pv_key_raw.decode("utf-8") if isinstance(pv_key_raw, bytes) else pv_key_raw
            obs_str = obs_raw.decode("utf-8") if isinstance(obs_raw, bytes) else obs_raw

            # Skip cleared
            if client.sismember(cleared_key, pv_key):
                continue

            # Skip already eliminated
            elim_key = cls.ELIMINATED_KEY.format(opt_id=optimization_id)
            if client.hexists(elim_key, pv_key):
                continue

            observations = json.loads(obs_str)
            if len(observations) < MIN_OBSERVATIONS:
                continue

            # Check if ALL observations are below threshold
            all_bad = all(
                obs["avg_pr"] < MIN_PAYOFF_RATIO for obs in observations
            )
            if all_bad:
                candidates.append((pv_key, len(observations)))

        if candidates:
            # Eliminate the one with most observations (strongest evidence)
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_pv_key, obs_count = candidates[0]

            # Parse param_name and param_value from key
            parts = best_pv_key.split(":", 1)
            if len(parts) == 2:
                param_name = parts[0]
                param_value = float(parts[1])

                obs_raw = client.hget(stats_key, best_pv_key)
                obs_str = obs_raw.decode("utf-8") if isinstance(obs_raw, bytes) else obs_raw
                observations = json.loads(obs_str)

                evidence = {
                    "method": "gradual",
                    "trigger_genome": genome_id,
                    "observations": [o["avg_pr"] for o in observations],
                    "count": obs_count,
                }
                cls._eliminate_param_value(
                    optimization_id, param_name, param_value, evidence
                )
                eliminated.append((param_name, param_value))

        return eliminated

    @classmethod
    def _eliminate_param_value(
        cls,
        optimization_id: str,
        param_name: str,
        param_value: Any,
        evidence: Dict[str, Any],
    ) -> None:
        """
        Eliminate a toxic parameter value:
        1. Load genome-params mapping
        2. Find all genome_ids containing this (param, value)
        3. Add them to skip_list SET
        4. Store evidence in eliminated HASH
        5. Log the event
        """
        client = cls.get_redis_client()
        pv_key = _param_value_key(param_name, param_value)

        # Store evidence (idempotent)
        elim_key = cls.ELIMINATED_KEY.format(opt_id=optimization_id)
        client.hset(elim_key, pv_key, json.dumps(evidence))

        # Find all genomes with this param value
        genome_params = cls._get_genome_params(optimization_id)
        skip_key = cls.SKIP_LIST_KEY.format(opt_id=optimization_id)

        value_rounded = round(float(param_value), 6)
        skipped_count = 0

        for gid, params in genome_params.items():
            if gid == "G_000":
                continue  # Never skip BASE

            gid_value = params.get(param_name)
            if gid_value is not None and round(float(gid_value), 6) == value_rounded:
                added = client.sadd(skip_key, gid)
                if added:
                    skipped_count += 1

        logger.info(
            f"SMART FILTER: Eliminated {param_name}={param_value}\n"
            f"  Evidence: {json.dumps(evidence)}\n"
            f"  Skipping {skipped_count} remaining genomes"
        )

    # --- Monitoring ---

    @classmethod
    def get_filtering_summary(cls, optimization_id: str) -> Dict[str, Any]:
        """Return summary dict for progress API and logging."""
        client = cls.get_redis_client()

        skip_key = cls.SKIP_LIST_KEY.format(opt_id=optimization_id)
        elim_key = cls.ELIMINATED_KEY.format(opt_id=optimization_id)

        genomes_skipped = client.scard(skip_key)

        eliminated_raw = client.hgetall(elim_key)
        eliminated_params = []
        for pv_key_raw, evidence_raw in eliminated_raw.items():
            pv_key = pv_key_raw.decode("utf-8") if isinstance(pv_key_raw, bytes) else pv_key_raw
            evidence_str = evidence_raw.decode("utf-8") if isinstance(evidence_raw, bytes) else evidence_raw
            evidence = json.loads(evidence_str)

            parts = pv_key.split(":", 1)
            if len(parts) == 2:
                eliminated_params.append({
                    "param": parts[0],
                    "value": float(parts[1]),
                    "after_genome": evidence.get("trigger_genome", "unknown"),
                    "method": evidence.get("method", "unknown"),
                    "observations": evidence.get("count", len(evidence.get("observations", []))),
                })

        return {
            "enabled": True,
            "genomes_skipped": genomes_skipped,
            "eliminated_params": eliminated_params,
        }

    @classmethod
    def cleanup(cls, optimization_id: str) -> None:
        """Remove all smart filtering Redis keys for an optimization."""
        client = cls.get_redis_client()
        keys = [
            cls.GENOMES_KEY.format(opt_id=optimization_id),
            cls.STATS_KEY.format(opt_id=optimization_id),
            cls.CLEARED_KEY.format(opt_id=optimization_id),
            cls.SKIP_LIST_KEY.format(opt_id=optimization_id),
            cls.SKIP_INCR_KEY.format(opt_id=optimization_id),
            cls.ELIMINATED_KEY.format(opt_id=optimization_id),
        ]
        for key in keys:
            client.delete(key)
