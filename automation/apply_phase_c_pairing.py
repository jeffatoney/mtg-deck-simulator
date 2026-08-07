from __future__ import annotations

import json
from pathlib import Path

ROOT = Path.cwd()


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    a = text.index(start)
    b = text.index(end, a)
    target.write_text(text[:a] + replacement + text[b:], encoding="utf-8")


# ---------------------------------------------------------------------------
# Frozen pilot configuration: 500 standard executions; 200 exploratory
# executions are the same environment seeds as a frozen 200-game subset of
# the standards. Search randomness has its own namespace.
# ---------------------------------------------------------------------------
config = {
    "authorization": {
        "approved_at": None,
        "approved_by": None,
        "confirmation_token": "AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY",
        "execution_allowed": False,
        "status": "LOCKED_PENDING_OWNER_APPROVAL",
    },
    "deck": {
        "commanders": [
            "Malcolm, Keen-Eyed Navigator",
            "Breeches, Brazen Plunderer",
        ],
        "exact_library_count": 98,
        "physical_card_count": 100,
        "source": "docs/source/decklist.txt",
    },
    "exploratory_search": {
        "bounded": True,
        "future_information_allowed": False,
        "post_result_optimization_allowed": False,
        "production_decision_layer_depth": 1,
        "reported_separately": True,
        "rules_validation_required": True,
    },
    "full_study": {
        "authorization_status": "LOCKED_PENDING_POST_PILOT_REVIEW",
        "execution_allowed": False,
        "exploratory_games": 5000,
        "standard_games": 20000,
    },
    "game_model": {
        "blocking_modeled": False,
        "breeches_unknown_cards_added_as_deterministic_resources": False,
        "controlled_player_draws_on_turn_one": True,
        "end_after_controlled_turn": 10,
        "glint_horn_may_attack_when_legal": True,
        "malcolm_may_connect_when_legal": True,
        "opponent_interaction_modeled": False,
        "opponent_wins_modeled": False,
        "opponents": 3,
        "players": 4,
    },
    "measurement": {
        "additional_checkpoints": [5, 6, 10],
        "objective": "MAXIMIZE_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "primary_checkpoint": 8,
        "required_outputs": [
            "opening_hand_records",
            "mulligan_depth",
            "checkpoint_table_win_access",
            "combo_access",
            "earliest_legal_attempt_turn",
            "actual_first_attempt_turn",
            "failure_labels",
            "card_measurements",
            "terminal_status",
            "replay_transcript",
            "immutable_run_manifest",
            "paired_turn8_analysis",
            "aggregation_digest",
        ],
    },
    "mulligan": {
        "candidate_hand_sizes": [7, 7, 6, 5, 4],
        "refill_kept_hand_to": 7,
        "rejected_hands_returned_and_shuffled": True,
        "stop_below_four": True,
    },
    "paired_analysis": {
        "bootstrap_resamples": 10000,
        "checkpoint_turn": 8,
        "confidence_interval_method": "DETERMINISTIC_PAIRED_BOOTSTRAP_PERCENTILE_V1",
        "confidence_level": 0.95,
        "mcnemar_test": "EXACT_TWO_SIDED",
        "outcome_name": "LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "paired_game_count": 200,
        "pairs_per_standard_shard": 20,
        "pair_selection_rule": "FIRST_20_OF_EACH_STANDARD_SHARD",
        "required_reporting_sentence": (
            "These figures measure combo assembly speed against opponents who take no actions. "
            "They are not win rates and do not predict performance against interactive opponents."
        ),
    },
    "pilot": {
        "environment_seed_namespace": "phase-c-pilot-environment-v1",
        "exploratory_games": 200,
        "exploratory_search_seed_namespace": "phase-c-pilot-exploratory-search-v1",
        "exploratory_shards": 10,
        "standard_games": 500,
        "standard_shards": 10,
    },
    "policy": {
        "evaluator_snapshot_id": "contextual_combo_v1",
        "evaluator_snapshot_sha256": "86c5e07daaa86362a38fad7a66d712443e32ba8af743bcaaa15576207264eca2",
        "exploratory_continuation_policy_config_id": "anchor_balanced",
        "learning_plan_sha256": "4884586c492c62cfd009c0a53c6d4ddd888274771c10efddc2b1853745a685e2",
        "policy_mutation_allowed": False,
        "standard_policy_config_hash": "d10bc384f254ab7684ea62b45340d86349f36e4d9786a9d639a9c7c6ce38f800",
        "standard_policy_config_id": "anchor_balanced",
    },
    "prerequisites": {
        "clean_engine_only": True,
        "legacy_import_allowed": False,
        "phase_a_verifier_required": "PASS",
        "phase_b_certification_required": "PASS",
        "phase_b_verifier_required": "PASS",
        "post_merge_main_ci_required": "PASS",
    },
    "schema_version": "phase-c-pilot-config-v2",
    "stop_conditions": [
        "PHASE_A_OR_PHASE_B_GATE_FAILURE",
        "SOURCE_OR_CONFIGURATION_DIGEST_DRIFT",
        "UNSUPPORTED_CAPABILITY_OR_STRATEGIC_BLOCKER",
        "HIDDEN_FUTURE_ACCESS",
        "POST_RESULT_POLICY_OPTIMIZATION",
        "LEGACY_EXECUTION_OR_IMPORT",
        "GAME_COUNT_OR_SEED_ASSIGNMENT_MISMATCH",
        "PAIRED_ENVIRONMENT_OR_SEARCH_SEED_MISMATCH",
        "STANDARD_EXPLORATORY_MODE_MIXING",
        "MANIFEST_REPLAY_OR_AGGREGATION_MISMATCH",
        "FULL_STUDY_ATTEMPT_BEFORE_SEPARATE_AUTHORIZATION",
    ],
}
(ROOT / "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json").write_text(
    json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)

pairing_module = '''"""Frozen paired-environment design and paired Turn-8 analysis for Phase C."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

PAIRED_GAME_COUNT = 200
PAIRS_PER_STANDARD_SHARD = 20
PAIRED_CHECKPOINT_TURN = 8
PAIRED_CI_METHOD = "DETERMINISTIC_PAIRED_BOOTSTRAP_PERCENTILE_V1"
PAIRED_CI_CONFIDENCE = 0.95
PAIRED_BOOTSTRAP_RESAMPLES = 10_000
PAIR_SELECTION_RULE = "FIRST_20_OF_EACH_STANDARD_SHARD"
REPORTING_SENTENCE = (
    "These figures measure combo assembly speed against opponents who take no actions. "
    "They are not win rates and do not predict performance against interactive opponents."
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _derive_seeds(namespace: str, count: int) -> tuple[int, ...]:
    return tuple(
        int.from_bytes(hashlib.sha256(f"{namespace}:{index}".encode()).digest()[:8], "big")
        for index in range(1, count + 1)
    )


def _pair_id(standard_game_index: int, environment_seed: int) -> str:
    return hashlib.sha256(
        f"phase-c-pair-v1:{standard_game_index}:{environment_seed}".encode()
    ).hexdigest()[:24]


@dataclass(frozen=True)
class PairingPlan:
    exploratory_environment_seeds: tuple[int, ...]
    exploratory_search_seeds: tuple[int, ...]
    paired_standard_game_indexes: tuple[int, ...]
    pair_ids: tuple[str, ...]
    exploratory_environment_sha256: str
    exploratory_search_sha256: str
    pair_assignment_sha256: str

    def __post_init__(self) -> None:
        fields = (
            self.exploratory_environment_seeds,
            self.exploratory_search_seeds,
            self.paired_standard_game_indexes,
            self.pair_ids,
        )
        if any(len(value) != PAIRED_GAME_COUNT for value in fields):
            raise ValueError("Phase C pairing plan must contain exactly 200 pairs")
        if len(set(self.exploratory_environment_seeds)) != PAIRED_GAME_COUNT:
            raise ValueError("paired environment seeds contain duplicates")
        if len(set(self.exploratory_search_seeds)) != PAIRED_GAME_COUNT:
            raise ValueError("exploratory search seeds contain duplicates")
        if len(set(self.paired_standard_game_indexes)) != PAIRED_GAME_COUNT:
            raise ValueError("paired standard game indexes contain duplicates")
        if len(set(self.pair_ids)) != PAIRED_GAME_COUNT:
            raise ValueError("pair IDs contain duplicates")
        if set(self.exploratory_environment_seeds).intersection(self.exploratory_search_seeds):
            raise ValueError("environment and search seed domains overlap")

    def assignment_rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "pair_id": pair_id,
                "standard_game_index": standard_index,
                "environment_seed": environment_seed,
                "search_seed": search_seed,
            }
            for pair_id, standard_index, environment_seed, search_seed in zip(
                self.pair_ids,
                self.paired_standard_game_indexes,
                self.exploratory_environment_seeds,
                self.exploratory_search_seeds,
                strict=True,
            )
        )


def build_pairing_plan(
    standard_environment_seeds: Sequence[int],
    *,
    search_seed_namespace: str,
    standard_shards: int,
) -> PairingPlan:
    standard = tuple(int(value) for value in standard_environment_seeds)
    if len(standard) != 500 or len(set(standard)) != 500:
        raise ValueError("paired pilot requires exactly 500 unique standard environment seeds")
    if standard_shards != 10 or len(standard) % standard_shards:
        raise ValueError("paired pilot requires ten equal standard shards")
    shard_size = len(standard) // standard_shards
    if shard_size != 50:
        raise ValueError("paired pilot standard shard size must be 50")
    paired_indexes = tuple(
        shard * shard_size + offset + 1
        for shard in range(standard_shards)
        for offset in range(PAIRS_PER_STANDARD_SHARD)
    )
    exploratory_environment = tuple(standard[index - 1] for index in paired_indexes)
    search_seeds = _derive_seeds(search_seed_namespace, PAIRED_GAME_COUNT)
    pair_ids = tuple(
        _pair_id(index, seed) for index, seed in zip(paired_indexes, exploratory_environment, strict=True)
    )
    rows = tuple(
        {
            "pair_id": pair_id,
            "standard_game_index": index,
            "environment_seed": env,
            "search_seed": search,
        }
        for pair_id, index, env, search in zip(
            pair_ids, paired_indexes, exploratory_environment, search_seeds, strict=True
        )
    )
    return PairingPlan(
        exploratory_environment_seeds=exploratory_environment,
        exploratory_search_seeds=search_seeds,
        paired_standard_game_indexes=paired_indexes,
        pair_ids=pair_ids,
        exploratory_environment_sha256=_digest(exploratory_environment),
        exploratory_search_sha256=_digest(search_seeds),
        pair_assignment_sha256=_digest(rows),
    )


def _mcnemar_exact_two_sided(exploratory_only: int, standard_only: int) -> float:
    discordant = exploratory_only + standard_only
    if discordant == 0:
        return 1.0
    lower = min(exploratory_only, standard_only)
    numerator = sum(math.comb(discordant, k) for k in range(lower + 1))
    p_value = min(1.0, 2.0 * numerator / (2**discordant))
    return p_value


def _paired_bootstrap_percentile_ci(
    differences: Sequence[int],
    *,
    resamples: int = PAIRED_BOOTSTRAP_RESAMPLES,
    confidence: float = PAIRED_CI_CONFIDENCE,
) -> tuple[float, float]:
    values = tuple(int(value) for value in differences)
    if len(values) != PAIRED_GAME_COUNT or any(value not in {-1, 0, 1} for value in values):
        raise ValueError("paired bootstrap requires exactly 200 {-1,0,1} differences")
    seed_material = _digest(
        {
            "method": PAIRED_CI_METHOD,
            "confidence": confidence,
            "resamples": resamples,
            "differences": values,
        }
    )
    rng = random.Random(int(seed_material[:16], 16))
    n = len(values)
    samples = [
        sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)
    ]
    samples.sort()
    alpha = (1.0 - confidence) / 2.0
    lower_index = max(0, int(math.floor((resamples - 1) * alpha)))
    upper_index = min(resamples - 1, int(math.ceil((resamples - 1) * (1.0 - alpha))))
    return samples[lower_index], samples[upper_index]


def build_paired_turn8_analysis(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(record) for record in records]
    if len(rows) != PAIRED_GAME_COUNT:
        raise ValueError("paired Turn-8 analysis requires exactly 200 records")
    pair_ids = [str(row.get("pair_id", "")) for row in rows]
    if any(not pair_id for pair_id in pair_ids) or len(set(pair_ids)) != PAIRED_GAME_COUNT:
        raise ValueError("paired Turn-8 analysis requires 200 unique pair IDs")
    both = standard_only = exploratory_only = neither = 0
    differences: list[int] = []
    for row in rows:
        standard = bool(row["standard_access"])
        exploratory = bool(row["exploratory_access"])
        if standard and exploratory:
            both += 1
        elif standard:
            standard_only += 1
        elif exploratory:
            exploratory_only += 1
        else:
            neither += 1
        differences.append(int(exploratory) - int(standard))
    standard_access_count = both + standard_only
    exploratory_access_count = both + exploratory_only
    difference = (exploratory_only - standard_only) / PAIRED_GAME_COUNT
    lower, upper = _paired_bootstrap_percentile_ci(differences)
    p_value = _mcnemar_exact_two_sided(exploratory_only, standard_only)
    return {
        "schema_version": "phase-c-paired-turn8-analysis-v1",
        "checkpoint_turn": PAIRED_CHECKPOINT_TURN,
        "pair_count": PAIRED_GAME_COUNT,
        "both_access": both,
        "standard_only_access": standard_only,
        "exploratory_only_access": exploratory_only,
        "neither_access": neither,
        "standard_access_count": standard_access_count,
        "exploratory_access_count": exploratory_access_count,
        "standard_access_rate": standard_access_count / PAIRED_GAME_COUNT,
        "exploratory_access_rate": exploratory_access_count / PAIRED_GAME_COUNT,
        "paired_access_rate_difference": difference,
        "discordant_pair_count": standard_only + exploratory_only,
        "mcnemar_test": "EXACT_TWO_SIDED",
        "mcnemar_exact_two_sided_p_value": p_value,
        "confidence_interval_method": PAIRED_CI_METHOD,
        "confidence_level": PAIRED_CI_CONFIDENCE,
        "bootstrap_resamples": PAIRED_BOOTSTRAP_RESAMPLES,
        "paired_access_rate_difference_ci": {"lower": lower, "upper": upper},
        "reporting_metric": "LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS",
        "required_reporting_sentence": REPORTING_SENTENCE,
        "pair_records_sha256": _digest(rows),
    }


__all__ = [
    "PAIR_SELECTION_RULE",
    "PAIRED_BOOTSTRAP_RESAMPLES",
    "PAIRED_CHECKPOINT_TURN",
    "PAIRED_CI_CONFIDENCE",
    "PAIRED_CI_METHOD",
    "PAIRED_GAME_COUNT",
    "PAIRS_PER_STANDARD_SHARD",
    "PairingPlan",
    "REPORTING_SENTENCE",
    "build_paired_turn8_analysis",
    "build_pairing_plan",
]
'''
(ROOT / "src/mtg_runs/phase_c_pairing.py").write_text(pairing_module, encoding="utf-8")

# ---------------------------------------------------------------------------
# phase_c.py: seed plan, shard assignment, config validation, readiness, and
# execution wiring.
# ---------------------------------------------------------------------------
replace_once(
    "src/mtg_runs/phase_c.py",
    "from typing import Any, Callable\n",
    "from typing import Any, Callable\n\nfrom mtg_runs.phase_c_pairing import (\n"
    "    PAIR_SELECTION_RULE,\n"
    "    PAIRED_BOOTSTRAP_RESAMPLES,\n"
    "    PAIRED_CHECKPOINT_TURN,\n"
    "    PAIRED_CI_CONFIDENCE,\n"
    "    PAIRED_CI_METHOD,\n"
    "    PAIRED_GAME_COUNT,\n"
    "    PAIRS_PER_STANDARD_SHARD,\n"
    "    REPORTING_SENTENCE,\n"
    "    build_pairing_plan,\n"
    ")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    seeds: tuple[int, ...]\n\n    def __post_init__(self) -> None:\n",
    "    seeds: tuple[int, ...]\n"
    "    pair_ids: tuple[str | None, ...]\n"
    "    paired_standard_game_indexes: tuple[int | None, ...]\n"
    "    search_seeds: tuple[int | None, ...]\n\n"
    "    def __post_init__(self) -> None:\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        if len(self.seeds) != len(set(self.seeds)):\n"
    "            raise PhaseCControlError(\"pilot shard contains duplicate seeds\")\n",
    "        if len(self.seeds) != len(set(self.seeds)):\n"
    "            raise PhaseCControlError(\"pilot shard contains duplicate seeds\")\n"
    "        if not (\n"
    "            len(self.pair_ids)\n"
    "            == len(self.paired_standard_game_indexes)\n"
    "            == len(self.search_seeds)\n"
    "            == len(self.seeds)\n"
    "        ):\n"
    "            raise PhaseCControlError(\"pilot shard pairing metadata does not match seed count\")\n"
    "        if self.mode == \"STANDARD\":\n"
    "            if any(value is not None for value in self.search_seeds):\n"
    "                raise PhaseCControlError(\"standard shard cannot contain exploratory search seeds\")\n"
    "        else:\n"
    "            if any(value is None for value in self.pair_ids):\n"
    "                raise PhaseCControlError(\"exploratory shard requires pair IDs\")\n"
    "            if any(value is None for value in self.paired_standard_game_indexes):\n"
    "                raise PhaseCControlError(\"exploratory shard requires paired standard indexes\")\n"
    "            if any(value is None for value in self.search_seeds):\n"
    "                raise PhaseCControlError(\"exploratory shard requires search seeds\")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "class PilotSeedPlan:\n"
    "    standard: tuple[int, ...]\n"
    "    exploratory: tuple[int, ...]\n"
    "    standard_sha256: str\n"
    "    exploratory_sha256: str\n",
    "class PilotSeedPlan:\n"
    "    standard: tuple[int, ...]\n"
    "    exploratory: tuple[int, ...]\n"
    "    exploratory_search: tuple[int, ...]\n"
    "    paired_standard_game_indexes: tuple[int, ...]\n"
    "    pair_ids: tuple[str, ...]\n"
    "    standard_sha256: str\n"
    "    exploratory_sha256: str\n"
    "    exploratory_search_sha256: str\n"
    "    pair_assignment_sha256: str\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        if len(set(self.exploratory)) != len(self.exploratory):\n"
    "            raise PhaseCControlError(\"exploratory pilot seed plan contains duplicates\")\n"
    "        if set(self.standard).intersection(self.exploratory):\n"
    "            raise PhaseCControlError(\"standard and exploratory pilot seed plans overlap\")\n",
    "        if len(set(self.exploratory)) != len(self.exploratory):\n"
    "            raise PhaseCControlError(\"exploratory paired environment seeds contain duplicates\")\n"
    "        if not set(self.exploratory).issubset(self.standard):\n"
    "            raise PhaseCControlError(\"exploratory environment seeds must be a standard subset\")\n"
    "        if len(self.exploratory_search) != EXPLORATORY_GAMES or len(set(self.exploratory_search)) != EXPLORATORY_GAMES:\n"
    "            raise PhaseCControlError(\"exploratory search seed plan must contain 200 unique seeds\")\n"
    "        if set(self.exploratory_search).intersection(self.standard):\n"
    "            raise PhaseCControlError(\"environment and search seed domains must not overlap\")\n"
    "        if len(self.paired_standard_game_indexes) != PAIRED_GAME_COUNT or len(self.pair_ids) != PAIRED_GAME_COUNT:\n"
    "            raise PhaseCControlError(\"paired pilot metadata must contain exactly 200 pairs\")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    standard_seed_namespace: str\n"
    "    exploratory_seed_namespace: str\n",
    "    environment_seed_namespace: str\n"
    "    exploratory_search_seed_namespace: str\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    standard_seed_sha256: str\n"
    "    exploratory_seed_sha256: str\n",
    "    standard_seed_sha256: str\n"
    "    exploratory_seed_sha256: str\n"
    "    exploratory_search_seed_sha256: str\n"
    "    pair_assignment_sha256: str\n"
    "    paired_game_count: int\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    prerequisites = _mapping(payload.get(\"prerequisites\"), \"prerequisites\")\n",
    "    prerequisites = _mapping(payload.get(\"prerequisites\"), \"prerequisites\")\n"
    "    paired = _mapping(payload.get(\"paired_analysis\"), \"paired_analysis\")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    _exact(prerequisites.get(\"post_merge_main_ci_required\"), \"PASS\", \"post-merge main CI\")\n",
    "    _exact(prerequisites.get(\"post_merge_main_ci_required\"), \"PASS\", \"post-merge main CI\")\n\n"
    "    _exact(paired.get(\"paired_game_count\"), PAIRED_GAME_COUNT, \"paired game count\")\n"
    "    _exact(paired.get(\"pairs_per_standard_shard\"), PAIRS_PER_STANDARD_SHARD, \"pairs per standard shard\")\n"
    "    _exact(paired.get(\"pair_selection_rule\"), PAIR_SELECTION_RULE, \"pair selection rule\")\n"
    "    _exact(paired.get(\"checkpoint_turn\"), PAIRED_CHECKPOINT_TURN, \"paired checkpoint\")\n"
    "    _exact(paired.get(\"mcnemar_test\"), \"EXACT_TWO_SIDED\", \"paired test\")\n"
    "    _exact(paired.get(\"confidence_interval_method\"), PAIRED_CI_METHOD, \"paired confidence interval\")\n"
    "    _exact(paired.get(\"confidence_level\"), PAIRED_CI_CONFIDENCE, \"paired confidence level\")\n"
    "    _exact(paired.get(\"bootstrap_resamples\"), PAIRED_BOOTSTRAP_RESAMPLES, \"paired bootstrap resamples\")\n"
    "    _exact(paired.get(\"required_reporting_sentence\"), REPORTING_SENTENCE, \"paired reporting sentence\")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    _exact(payload.get(\"schema_version\"), \"phase-c-pilot-config-v1\", \"schema\")\n",
    "    _exact(payload.get(\"schema_version\"), \"phase-c-pilot-config-v2\", \"schema\")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    standard_namespace = str(pilot.get(\"standard_seed_namespace\", \"\"))\n"
    "    exploratory_namespace = str(pilot.get(\"exploratory_seed_namespace\", \"\"))\n"
    "    if not standard_namespace or not exploratory_namespace:\n"
    "        raise PhaseCControlError(\"pilot seed namespaces must be nonempty\")\n"
    "    if standard_namespace == exploratory_namespace:\n"
    "        raise PhaseCControlError(\"pilot seed namespaces must be distinct\")\n",
    "    environment_namespace = str(pilot.get(\"environment_seed_namespace\", \"\"))\n"
    "    search_namespace = str(pilot.get(\"exploratory_search_seed_namespace\", \"\"))\n"
    "    if not environment_namespace or not search_namespace:\n"
    "        raise PhaseCControlError(\"environment and exploratory search seed namespaces must be nonempty\")\n"
    "    if environment_namespace == search_namespace:\n"
    "        raise PhaseCControlError(\"environment and exploratory search seed namespaces must be distinct\")\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        standard_seed_namespace=standard_namespace,\n"
    "        exploratory_seed_namespace=exploratory_namespace,\n",
    "        environment_seed_namespace=environment_namespace,\n"
    "        exploratory_search_seed_namespace=search_namespace,\n",
)
replace_between(
    "src/mtg_runs/phase_c.py",
    "def build_pilot_seed_plan(config: PhaseCConfiguration) -> PilotSeedPlan:\n",
    "\n\ndef build_pilot_shard_assignment(\n",
    '''def build_pilot_seed_plan(config: PhaseCConfiguration) -> PilotSeedPlan:\n    standard = _derive_seeds(config.environment_seed_namespace, config.standard_games)\n    pairing = build_pairing_plan(\n        standard,\n        search_seed_namespace=config.exploratory_search_seed_namespace,\n        standard_shards=config.standard_shards,\n    )\n    return PilotSeedPlan(\n        standard=standard,\n        exploratory=pairing.exploratory_environment_seeds,\n        exploratory_search=pairing.exploratory_search_seeds,\n        paired_standard_game_indexes=pairing.paired_standard_game_indexes,\n        pair_ids=pairing.pair_ids,\n        standard_sha256=hashlib.sha256(_canonical(standard)).hexdigest(),\n        exploratory_sha256=pairing.exploratory_environment_sha256,\n        exploratory_search_sha256=pairing.exploratory_search_sha256,\n        pair_assignment_sha256=pairing.pair_assignment_sha256,\n    )\n''',
)
replace_between(
    "src/mtg_runs/phase_c.py",
    "def build_pilot_shard_assignment(\n",
    "\n\ndef _combo_detector_smoke()",
    '''def build_pilot_shard_assignment(\n    config: PhaseCConfiguration,\n    seeds: PilotSeedPlan,\n    *,\n    mode: str,\n    shard_index: int,\n) -> PilotShardAssignment:\n    pair_by_standard_index = dict(zip(seeds.paired_standard_game_indexes, seeds.pair_ids, strict=True))\n    if mode == "STANDARD":\n        values = seeds.standard\n        shard_count = config.standard_shards\n        if len(values) % shard_count:\n            raise PhaseCControlError("pilot game count must divide evenly across frozen shards")\n        if shard_index < 0 or shard_index >= shard_count:\n            raise PhaseCControlError("pilot shard index is outside the frozen shard range")\n        size = len(values) // shard_count\n        start = shard_index * size\n        selected = tuple(values[start : start + size])\n        standard_indexes = tuple(range(start + 1, start + size + 1))\n        return PilotShardAssignment(\n            mode=mode,\n            shard_index=shard_index,\n            shard_count=shard_count,\n            first_game_index=start + 1,\n            last_game_index=start + size,\n            seeds=selected,\n            pair_ids=tuple(pair_by_standard_index.get(index) for index in standard_indexes),\n            paired_standard_game_indexes=tuple(\n                index if index in pair_by_standard_index else None for index in standard_indexes\n            ),\n            search_seeds=(None,) * size,\n        )\n    if mode == "EXPLORATORY":\n        values = seeds.exploratory\n        shard_count = config.exploratory_shards\n        if len(values) % shard_count:\n            raise PhaseCControlError("pilot game count must divide evenly across frozen shards")\n        if shard_index < 0 or shard_index >= shard_count:\n            raise PhaseCControlError("pilot shard index is outside the frozen shard range")\n        size = len(values) // shard_count\n        start = shard_index * size\n        return PilotShardAssignment(\n            mode=mode,\n            shard_index=shard_index,\n            shard_count=shard_count,\n            first_game_index=start + 1,\n            last_game_index=start + size,\n            seeds=tuple(values[start : start + size]),\n            pair_ids=tuple(seeds.pair_ids[start : start + size]),\n            paired_standard_game_indexes=tuple(\n                seeds.paired_standard_game_indexes[start : start + size]\n            ),\n            search_seeds=tuple(seeds.exploratory_search[start : start + size]),\n        )\n    raise PhaseCControlError("pilot shard mode must be STANDARD or EXPLORATORY")\n''',
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        run_phase_c_combat_smoke,\n"
    "        run_phase_c_exploratory_smoke,\n",
    "        run_phase_c_combat_smoke,\n"
    "        run_phase_c_exploratory_smoke,\n"
    "        run_phase_c_paired_environment_smoke,\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    run(\"EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED\", run_phase_c_exploratory_smoke)\n"
    "    run(\"COMBO_ACCESS_DETECTORS_INCOMPLETE\", _combo_detector_smoke)\n",
    "    run(\"EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED\", run_phase_c_exploratory_smoke)\n"
    "    run(\"PAIRED_EXPLORATORY_DESIGN_NOT_IMPLEMENTED\", run_phase_c_paired_environment_smoke)\n"
    "    run(\"COMBO_ACCESS_DETECTORS_INCOMPLETE\", _combo_detector_smoke)\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        exploratory_seed_sha256=seeds.exploratory_sha256,\n"
    "        execution_allowed=config.execution_allowed,\n",
    "        exploratory_seed_sha256=seeds.exploratory_sha256,\n"
    "        exploratory_search_seed_sha256=seeds.exploratory_search_sha256,\n"
    "        pair_assignment_sha256=seeds.pair_assignment_sha256,\n"
    "        paired_game_count=PAIRED_GAME_COUNT,\n"
    "        execution_allowed=config.execution_allowed,\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    for offset, seed in enumerate(assignment.seeds):\n"
    "        global_index = assignment.first_game_index + offset\n"
    "        execution = run_phase_c_game_execution(\n"
    "            seed=seed,\n"
    "            mode=mode,\n",
    "    for offset, seed in enumerate(assignment.seeds):\n"
    "        global_index = assignment.first_game_index + offset\n"
    "        execution = run_phase_c_game_execution(\n"
    "            seed=seed,\n"
    "            mode=mode,\n"
    "            search_seed=assignment.search_seeds[offset],\n"
    "            pair_id=assignment.pair_ids[offset],\n"
    "            paired_standard_game_index=assignment.paired_standard_game_indexes[offset],\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        seeds=assignment.seeds,\n"
    "        implementation_commit=context.implementation_commit,\n",
    "        seeds=assignment.seeds,\n"
    "        pair_ids=assignment.pair_ids,\n"
    "        paired_standard_game_indexes=assignment.paired_standard_game_indexes,\n"
    "        search_seeds=assignment.search_seeds,\n"
    "        implementation_commit=context.implementation_commit,\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        expected_exploratory_seeds=seeds.exploratory,\n"
    "        expected_standard_shards=config.standard_shards,\n",
    "        expected_exploratory_seeds=seeds.exploratory,\n"
    "        expected_exploratory_search_seeds=seeds.exploratory_search,\n"
    "        expected_pair_ids=seeds.pair_ids,\n"
    "        expected_paired_standard_game_indexes=seeds.paired_standard_game_indexes,\n"
    "        expected_standard_shards=config.standard_shards,\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "    manifest, standard_summary, exploratory_summary = validate_phase_c_aggregate(\n",
    "    manifest, standard_summary, exploratory_summary, paired_analysis = validate_phase_c_aggregate(\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        output_root, manifest, standard_summary, exploratory_summary\n"
    "    )\n",
    "        output_root, manifest, standard_summary, exploratory_summary, paired_analysis\n"
    "    )\n",
)
replace_once(
    "src/mtg_runs/phase_c.py",
    "        \"aggregation_sha256\": manifest.aggregation_sha256,\n"
    "        \"output\": str(aggregate_dir),\n",
    "        \"aggregation_sha256\": manifest.aggregation_sha256,\n"
    "        \"paired_turn8_analysis\": dict(paired_analysis),\n"
    "        \"output\": str(aggregate_dir),\n",
)

# ---------------------------------------------------------------------------
# Runner: mode-independent environment seed, separate exploratory search seed,
# and no fake same-game paired outcome record.
# ---------------------------------------------------------------------------
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "    DivergenceMeasurement,\n",
    "",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "    seed: int\n"
    "    policy_config_id: str\n",
    "    seed: int\n"
    "    environment_initial_state_hash: str\n"
    "    search_seed: int | None\n"
    "    pair_id: str | None\n"
    "    paired_standard_game_index: int | None\n"
    "    policy_config_id: str\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "        if self.mode == \"STANDARD\" and self.exploratory_decision_layer_depth != 0:\n"
    "            raise ValueError(\"standard technical games cannot report exploratory depth\")\n"
    "        if self.mode == \"EXPLORATORY\" and self.exploratory_decision_layer_depth != 1:\n",
    "        if self.mode == \"STANDARD\" and self.exploratory_decision_layer_depth != 0:\n"
    "            raise ValueError(\"standard technical games cannot report exploratory depth\")\n"
    "        if self.mode == \"STANDARD\" and self.search_seed is not None:\n"
    "            raise ValueError(\"standard technical games cannot consume exploratory search seeds\")\n"
    "        if self.mode == \"EXPLORATORY\" and self.search_seed is None:\n"
    "            raise ValueError(\"exploratory technical games require a separate search seed\")\n"
    "        if self.mode == \"EXPLORATORY\" and self.exploratory_decision_layer_depth != 1:\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "    def __init__(self, policy_config_id: str, game_seed: int) -> None:\n"
    "        self.policy_config_id = policy_config_id\n"
    "        self.game_seed = game_seed\n",
    "    def __init__(self, policy_config_id: str, search_seed: int) -> None:\n"
    "        self.policy_config_id = policy_config_id\n"
    "        self.search_seed = search_seed\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "                f\"phase-c-belief:{self.game_seed}:{executor.state.turn.number}:\"\n",
    "                f\"phase-c-belief:{self.search_seed}:{executor.state.turn.number}:\"\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "    capture: _GameMeasurementCapture,\n"
    "    exploratory_records: tuple[ExploratoryDecisionRecord, ...],\n",
    "    capture: _GameMeasurementCapture,\n"
    "    exploratory_records: tuple[ExploratoryDecisionRecord, ...],\n"
    "    environment_initial_state_hash: str,\n"
    "    search_seed: int | None,\n"
    "    pair_id: str | None,\n"
    "    paired_standard_game_index: int | None,\n",
)
replace_between(
    "src/mtg_runs/phase_c_runner.py",
    "    divergence: DivergenceMeasurement | None = None\n",
    "\n    usable_protection = int(\n",
    '''    # Single exploratory executions record choice divergence diagnostics only.\n    # Paired outcome comparison is constructed later from two executions sharing\n    # the same environment seed; never write the same game's result into both arms.\n    first_divergence = next(\n        (record for record in exploratory_records if record.first_divergence), None\n    )\n    divergence = None\n''',
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "        extra={\n"
    "            \"selected_actions\": tuple(capture.selected_actions),\n",
    "        extra={\n"
    "            \"environment_seed\": seed,\n"
    "            \"environment_initial_state_hash\": environment_initial_state_hash,\n"
    "            \"search_seed\": search_seed,\n"
    "            \"pair_id\": pair_id,\n"
    "            \"paired_standard_game_index\": paired_standard_game_index,\n"
    "            \"first_decision_divergence\": (\n"
    "                None if first_divergence is None else asdict(first_divergence)\n"
    "            ),\n"
    "            \"selected_actions\": tuple(capture.selected_actions),\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "    mode: str,\n"
    "    policy_config_id: str = \"anchor_balanced\",\n",
    "    mode: str,\n"
    "    search_seed: int | None = None,\n"
    "    pair_id: str | None = None,\n"
    "    paired_standard_game_index: int | None = None,\n"
    "    policy_config_id: str = \"anchor_balanced\",\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "    seed_text = f\"phase-c:{mode.lower()}:{seed}\"\n"
    "    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)\n",
    "    if mode == \"STANDARD\" and search_seed is not None:\n"
    "        raise ValueError(\"STANDARD execution cannot receive an exploratory search seed\")\n"
    "    effective_search_seed = search_seed\n"
    "    if mode == \"EXPLORATORY\" and effective_search_seed is None:\n"
    "        effective_search_seed = int.from_bytes(\n"
    "            hashlib.sha256(f\"phase-c-technical-search-v1:{seed}\".encode()).digest()[:8],\n"
    "            \"big\",\n"
    "        )\n"
    "    seed_text = f\"phase-c:environment:{seed}\"\n"
    "    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)\n"
    "    environment_initial_state_hash = state_hash(state)\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "        _OneLayerExplorer(policy_config_id, seed)\n"
    "        if mode == \"EXPLORATORY\" and policy_actions\n",
    "        _OneLayerExplorer(policy_config_id, int(effective_search_seed))\n"
    "        if mode == \"EXPLORATORY\" and policy_actions\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "        seed=seed,\n"
    "        policy_config_id=policy_config_id,\n",
    "        seed=seed,\n"
    "        environment_initial_state_hash=environment_initial_state_hash,\n"
    "        search_seed=effective_search_seed,\n"
    "        pair_id=pair_id,\n"
    "        paired_standard_game_index=paired_standard_game_index,\n"
    "        policy_config_id=policy_config_id,\n",
)
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "        exploratory_records=exploratory_records,\n"
    "    )\n",
    "        exploratory_records=exploratory_records,\n"
    "        environment_initial_state_hash=environment_initial_state_hash,\n"
    "        search_seed=effective_search_seed,\n"
    "        pair_id=pair_id,\n"
    "        paired_standard_game_index=paired_standard_game_index,\n"
    "    )\n",
)
paired_smoke = '''\n\ndef run_phase_c_paired_environment_smoke(\n    *, environment_seed: int = 505, search_seed: int = 606\n) -> dict[str, Any]:\n    \"\"\"Prove paired modes start from the same environment and separate search RNG.\"\"\"\n    pair_id = hashlib.sha256(f\"technical-pair:{environment_seed}\".encode()).hexdigest()[:24]\n    standard = run_phase_c_game_execution(\n        seed=environment_seed,\n        mode=\"STANDARD\",\n        pair_id=pair_id,\n        paired_standard_game_index=1,\n        through_turn=1,\n        validate_fresh_replay=False,\n        policy_actions=True,\n    )\n    exploratory = run_phase_c_game_execution(\n        seed=environment_seed,\n        mode=\"EXPLORATORY\",\n        search_seed=search_seed,\n        pair_id=pair_id,\n        paired_standard_game_index=1,\n        through_turn=1,\n        validate_fresh_replay=False,\n        policy_actions=True,\n    )\n    if (\n        standard.technical_game.environment_initial_state_hash\n        != exploratory.technical_game.environment_initial_state_hash\n    ):\n        raise UnsupportedCapability(\"paired modes did not share the same environment state\")\n    if standard.technical_game.opening_hands != exploratory.technical_game.opening_hands:\n        raise UnsupportedCapability(\"paired modes did not share the same opening environment\")\n    if standard.technical_game.search_seed is not None:\n        raise UnsupportedCapability(\"standard mode consumed a search seed\")\n    if exploratory.technical_game.search_seed != search_seed:\n        raise UnsupportedCapability(\"exploratory mode did not bind its separate search seed\")\n    return {\n        \"status\": \"PASS\",\n        \"pair_id\": pair_id,\n        \"environment_seed\": environment_seed,\n        \"search_seed\": search_seed,\n        \"environment_initial_state_hash\": standard.technical_game.environment_initial_state_hash,\n        \"opening_environment_equal\": True,\n        \"standard_search_seed\": None,\n        \"exploratory_search_seed\": search_seed,\n    }\n'''
replace_once(
    "src/mtg_runs/phase_c_runner.py",
    "\ndef run_phase_c_combat_smoke(*, seed: int = 303) -> dict[str, Any]:\n",
    paired_smoke + "\n\ndef run_phase_c_combat_smoke(*, seed: int = 303) -> dict[str, Any]:\n",
)

# ---------------------------------------------------------------------------
# Artifacts: persist pairing/search identity in shard manifests and compute a
# real paired Turn-8 outcome analysis at aggregation.
# ---------------------------------------------------------------------------
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "from typing import Any, Mapping, Sequence\n",
    "from typing import Any, Mapping, Sequence\n\n"
    "from mtg_runs.phase_c_pairing import (\n"
    "    PAIRED_GAME_COUNT,\n"
    "    build_paired_turn8_analysis,\n"
    ")\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "    seeds: tuple[int, ...]\n"
    "    implementation_commit: str\n",
    "    seeds: tuple[int, ...]\n"
    "    pair_ids: tuple[str | None, ...]\n"
    "    paired_standard_game_indexes: tuple[int | None, ...]\n"
    "    search_seeds: tuple[int | None, ...]\n"
    "    implementation_commit: str\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "    seed_sha256: str\n"
    "    technical_games_sha256: str\n",
    "    seed_sha256: str\n"
    "    pairing_sha256: str\n"
    "    search_seed_sha256: str\n"
    "    technical_games_sha256: str\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "        if len(self.seeds) != len(set(self.seeds)):\n"
    "            raise ValueError(\"Phase C shard contains duplicate seeds\")\n",
    "        if len(self.seeds) != len(set(self.seeds)):\n"
    "            raise ValueError(\"Phase C shard contains duplicate seeds\")\n"
    "        if not (len(self.pair_ids) == len(self.paired_standard_game_indexes) == len(self.search_seeds) == len(self.seeds)):\n"
    "            raise ValueError(\"Phase C shard pairing metadata length mismatch\")\n"
    "        nonempty_pair_ids = [value for value in self.pair_ids if value is not None]\n"
    "        if len(nonempty_pair_ids) != len(set(nonempty_pair_ids)):\n"
    "            raise ValueError(\"Phase C shard contains duplicate pair IDs\")\n"
    "        if any(value is not None and (len(value) != 24 or any(char not in '0123456789abcdef' for char in value)) for value in self.pair_ids):\n"
    "            raise ValueError(\"Phase C pair IDs must be lowercase 24-character hex values\")\n"
    "        if self.mode == \"STANDARD\" and any(value is not None for value in self.search_seeds):\n"
    "            raise ValueError(\"standard shard cannot contain exploratory search seeds\")\n"
    "        if self.mode == \"EXPLORATORY\" and (any(value is None for value in self.pair_ids) or any(value is None for value in self.paired_standard_game_indexes) or any(value is None for value in self.search_seeds)):\n"
    "            raise ValueError(\"exploratory shard requires complete pairing/search metadata\")\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "            (\"seed digest\", self.seed_sha256),\n"
    "            (\"technical-game digest\", self.technical_games_sha256),\n",
    "            (\"seed digest\", self.seed_sha256),\n"
    "            (\"pairing digest\", self.pairing_sha256),\n"
    "            (\"search-seed digest\", self.search_seed_sha256),\n"
    "            (\"technical-game digest\", self.technical_games_sha256),\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "    exploratory_seed_sha256: str\n"
    "    standard_shard_count: int\n",
    "    exploratory_seed_sha256: str\n"
    "    exploratory_search_seed_sha256: str\n"
    "    pair_assignment_sha256: str\n"
    "    paired_game_count: int\n"
    "    paired_analysis_sha256: str\n"
    "    standard_shard_count: int\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "        if self.schema_version != \"phase-c-pilot-aggregate-manifest-v1\":\n",
    "        if self.schema_version != \"phase-c-pilot-aggregate-manifest-v2\":\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "            (\"exploratory seed digest\", self.exploratory_seed_sha256),\n"
    "            (\"standard summary digest\", self.standard_summary_sha256),\n",
    "            (\"exploratory seed digest\", self.exploratory_seed_sha256),\n"
    "            (\"exploratory search seed digest\", self.exploratory_search_seed_sha256),\n"
    "            (\"pair assignment digest\", self.pair_assignment_sha256),\n"
    "            (\"paired analysis digest\", self.paired_analysis_sha256),\n"
    "            (\"standard summary digest\", self.standard_summary_sha256),\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "        if self.standard_game_count != 500 or self.exploratory_game_count != 200:\n"
    "            raise ValueError(\"Phase C aggregate must contain exactly 500/200 games\")\n",
    "        if self.standard_game_count != 500 or self.exploratory_game_count != 200:\n"
    "            raise ValueError(\"Phase C aggregate must contain exactly 500/200 games\")\n"
    "        if self.paired_game_count != PAIRED_GAME_COUNT:\n"
    "            raise ValueError(\"Phase C aggregate must contain exactly 200 paired comparisons\")\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "    seeds: Sequence[int],\n"
    "    implementation_commit: str,\n",
    "    seeds: Sequence[int],\n"
    "    pair_ids: Sequence[str | None],\n"
    "    paired_standard_game_indexes: Sequence[int | None],\n"
    "    search_seeds: Sequence[int | None],\n"
    "    implementation_commit: str,\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "        \"seeds\": seed_tuple,\n"
    "        \"implementation_commit\": implementation_commit,\n",
    "        \"seeds\": seed_tuple,\n"
    "        \"pair_ids\": tuple(pair_ids),\n"
    "        \"paired_standard_game_indexes\": tuple(paired_standard_game_indexes),\n"
    "        \"search_seeds\": tuple(search_seeds),\n"
    "        \"implementation_commit\": implementation_commit,\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "        \"seed_sha256\": _digest(seed_tuple),\n"
    "        \"technical_games_sha256\": _digest(technical_dicts),\n",
    "        \"seed_sha256\": _digest(seed_tuple),\n"
    "        \"pairing_sha256\": _digest(\n"
    "            [\n"
    "                {\"pair_id\": pair_id, \"standard_game_index\": standard_index, \"environment_seed\": seed}\n"
    "                for pair_id, standard_index, seed in zip(pair_ids, paired_standard_game_indexes, seed_tuple, strict=True)\n"
    "            ]\n"
    "        ),\n"
    "        \"search_seed_sha256\": _digest(tuple(search_seeds)),\n"
    "        \"technical_games_sha256\": _digest(technical_dicts),\n",
)
# Validate per-game pairing/search linkage.
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "    for expected_index, expected_seed, game, technical, replay, measurement in zip(\n"
    "        expected_indexes,\n"
    "        manifest.seeds,\n"
    "        game_records,\n"
    "        technical_games,\n"
    "        replays,\n"
    "        measurements,\n"
    "        strict=True,\n"
    "    ):\n",
    "    for expected_index, expected_seed, expected_pair_id, expected_standard_index, expected_search_seed, game, technical, replay, measurement in zip(\n"
    "        expected_indexes,\n"
    "        manifest.seeds,\n"
    "        manifest.pair_ids,\n"
    "        manifest.paired_standard_game_indexes,\n"
    "        manifest.search_seeds,\n"
    "        game_records,\n"
    "        technical_games,\n"
    "        replays,\n"
    "        measurements,\n"
    "        strict=True,\n"
    "    ):\n",
)
replace_once(
    "src/mtg_runs/phase_c_artifacts.py",
    "        if int(technical.get(\"seed\", -1)) != expected_seed:\n"
    "            raise ValueError(\"Phase C technical-game seed differs from the shard manifest\")\n",
    "        if int(technical.get(\"seed\", -1)) != expected_seed:\n"
    "            raise ValueError(\"Phase C technical-game seed differs from the shard manifest\")\n"
    "        if technical.get(\"pair_id\") != expected_pair_id or measurement.extra.get(\"pair_id\") != expected_pair_id:\n"
    "            raise ValueError(\"Phase C per-game pair ID linkage is inconsistent\")\n"
    "        if technical.get(\"paired_standard_game_index\") != expected_standard_index or measurement.extra.get(\"paired_standard_game_index\") != expected_standard_index:\n"
    "            raise ValueError(\"Phase C paired standard index linkage is inconsistent\")\n"
    "        if technical.get(\"search_seed\") != expected_search_seed or measurement.extra.get(\"search_seed\") != expected_search_seed:\n"
    "            raise ValueError(\"Phase C per-game search seed linkage is inconsistent\")\n"
    "        if measurement.extra.get(\"environment_seed\") != expected_seed:\n"
    "            raise ValueError(\"Phase C measurement environment seed linkage is inconsistent\")\n",
)

aggregate_replacement = '''def validate_phase_c_aggregate(\n    shard_dirs: Sequence[Path],\n    *,\n    expected_standard_seeds: Sequence[int],\n    expected_exploratory_seeds: Sequence[int],\n    expected_exploratory_search_seeds: Sequence[int],\n    expected_pair_ids: Sequence[str],\n    expected_paired_standard_game_indexes: Sequence[int],\n    expected_standard_shards: int,\n    expected_exploratory_shards: int,\n) -> tuple[PhaseCAggregateManifest, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:\n    if not shard_dirs:\n        raise ValueError("Phase C aggregation requires shard artifacts")\n    loaded = [load_phase_c_shard(path) for path in shard_dirs]\n    manifests = [value[0] for value in loaded]\n    invariant_fields = (\n        "implementation_commit",\n        "implementation_tree",\n        "activation_commit",\n        "locked_config_sha256",\n        "workflow_sha256",\n        "approval_record_sha256",\n        "policy_config_id",\n        "policy_config_sha256",\n        "evaluator_snapshot_id",\n        "evaluator_snapshot_sha256",\n        "learning_plan_sha256",\n        "pilot_authorized",\n    )\n    first = manifests[0]\n    for manifest in manifests[1:]:\n        mixed = [field for field in invariant_fields if getattr(manifest, field) != getattr(first, field)]\n        if mixed:\n            raise ValueError(f"Phase C aggregation rejects mixed shard identity fields: {mixed}")\n\n    mode_data: dict[str, list[tuple[PhaseCShardManifest, tuple[GameMeasurement, ...]]]] = {\n        "STANDARD": [],\n        "EXPLORATORY": [],\n    }\n    for manifest, _games, _replays, shard_measurements, _summary in loaded:\n        mode_data[manifest.mode].append((manifest, shard_measurements))\n\n    expected_standard = tuple(int(v) for v in expected_standard_seeds)\n    expected_exploratory = tuple(int(v) for v in expected_exploratory_seeds)\n    expected_search = tuple(int(v) for v in expected_exploratory_search_seeds)\n    expected_pairs = tuple(str(v) for v in expected_pair_ids)\n    expected_standard_indexes = tuple(int(v) for v in expected_paired_standard_game_indexes)\n    if not (\n        len(expected_exploratory)\n        == len(expected_search)\n        == len(expected_pairs)\n        == len(expected_standard_indexes)\n        == PAIRED_GAME_COUNT\n    ):\n        raise ValueError("Phase C paired aggregate expectations must contain exactly 200 pairs")\n    pair_by_standard_index = dict(zip(expected_standard_indexes, expected_pairs, strict=True))\n    expected_pair_by_mode = {\n        "STANDARD": tuple(pair_by_standard_index.get(index) for index in range(1, len(expected_standard) + 1)),\n        "EXPLORATORY": expected_pairs,\n    }\n    expected_index_by_mode = {\n        "STANDARD": tuple(index if index in pair_by_standard_index else None for index in range(1, len(expected_standard) + 1)),\n        "EXPLORATORY": expected_standard_indexes,\n    }\n    expected_search_by_mode = {\n        "STANDARD": (None,) * len(expected_standard),\n        "EXPLORATORY": expected_search,\n    }\n    expected_by_mode = {\n        "STANDARD": (expected_standard, expected_standard_shards),\n        "EXPLORATORY": (expected_exploratory, expected_exploratory_shards),\n    }\n    summaries: dict[str, Mapping[str, Any]] = {}\n    all_manifest_shas: list[str] = []\n    mode_measurements: dict[str, list[GameMeasurement]] = {}\n    for mode, entries in mode_data.items():\n        expected_seeds, expected_shards = expected_by_mode[mode]\n        if len(entries) != expected_shards:\n            raise ValueError(f"Phase C aggregation requires exactly {expected_shards} {mode} shards")\n        entries.sort(key=lambda value: value[0].shard_index)\n        if [manifest.shard_index for manifest, _ in entries] != list(range(expected_shards)):\n            raise ValueError(f"Phase C aggregation rejects missing or duplicate {mode} shard indexes")\n        flattened_seeds: list[int] = []\n        flattened_indexes: list[int] = []\n        flattened_pair_ids: list[str | None] = []\n        flattened_standard_indexes: list[int | None] = []\n        flattened_search_seeds: list[int | None] = []\n        measurements: list[GameMeasurement] = []\n        expected_next = 1\n        for manifest, shard_measurements in entries:\n            if manifest.shard_count != expected_shards:\n                raise ValueError(f"Phase C {mode} shard count declaration is inconsistent")\n            if manifest.first_game_index != expected_next:\n                raise ValueError(f"Phase C aggregation rejects {mode} game-index gaps or overlaps")\n            expected_next = manifest.last_game_index + 1\n            flattened_seeds.extend(manifest.seeds)\n            flattened_indexes.extend(range(manifest.first_game_index, manifest.last_game_index + 1))\n            flattened_pair_ids.extend(manifest.pair_ids)\n            flattened_standard_indexes.extend(manifest.paired_standard_game_indexes)\n            flattened_search_seeds.extend(manifest.search_seeds)\n            measurements.extend(shard_measurements)\n            all_manifest_shas.append(manifest.shard_sha256)\n        if tuple(flattened_seeds) != expected_seeds:\n            raise ValueError(f"Phase C aggregation rejects {mode} environment seed partition drift")\n        if tuple(flattened_pair_ids) != expected_pair_by_mode[mode]:\n            raise ValueError(f"Phase C aggregation rejects {mode} pair assignment drift")\n        if tuple(flattened_standard_indexes) != expected_index_by_mode[mode]:\n            raise ValueError(f"Phase C aggregation rejects {mode} paired standard-index drift")\n        if tuple(flattened_search_seeds) != expected_search_by_mode[mode]:\n            raise ValueError(f"Phase C aggregation rejects {mode} search-seed drift")\n        if flattened_indexes != list(range(1, len(expected_seeds) + 1)):\n            raise ValueError(f"Phase C aggregation rejects {mode} game-index drift")\n        if [record.game_index for record in measurements] != flattened_indexes:\n            raise ValueError(f"Phase C aggregation rejects {mode} measurement-index drift")\n        if [record.seed for record in measurements] != flattened_seeds:\n            raise ValueError(f"Phase C aggregation rejects {mode} measurement-seed drift")\n        summary = aggregate_measurements(measurements)\n        summaries[mode] = asdict(summary)\n        mode_measurements[mode] = measurements\n\n    standard_by_index = {record.game_index: record for record in mode_measurements["STANDARD"]}\n    exploratory_measurements = mode_measurements["EXPLORATORY"]\n    pair_records: list[dict[str, Any]] = []\n    for exploratory_index, (pair_id, standard_index, environment_seed, search_seed) in enumerate(\n        zip(expected_pairs, expected_standard_indexes, expected_exploratory, expected_search, strict=True),\n        start=1,\n    ):\n        standard_record = standard_by_index[standard_index]\n        exploratory_record = exploratory_measurements[exploratory_index - 1]\n        if standard_record.seed != environment_seed or exploratory_record.seed != environment_seed:\n            raise ValueError("paired STANDARD/EXPLORATORY executions do not share environment seed")\n        if exploratory_record.extra.get("search_seed") != search_seed:\n            raise ValueError("paired exploratory measurement lost its search seed binding")\n        if standard_record.extra.get("search_seed") is not None:\n            raise ValueError("paired standard measurement consumed exploratory search randomness")\n        if standard_record.extra.get("pair_id") != pair_id or exploratory_record.extra.get("pair_id") != pair_id:\n            raise ValueError("paired measurements do not share the exact pair ID")\n        if (\n            standard_record.extra.get("environment_initial_state_hash")\n            != exploratory_record.extra.get("environment_initial_state_hash")\n        ):\n            raise ValueError("paired executions did not start from the same environment state")\n        pair_records.append(\n            {\n                "pair_id": pair_id,\n                "standard_game_index": standard_index,\n                "exploratory_game_index": exploratory_index,\n                "environment_seed": environment_seed,\n                "search_seed": search_seed,\n                "standard_access": bool(standard_record.checkpoint_table_win_access[8]),\n                "exploratory_access": bool(exploratory_record.checkpoint_table_win_access[8]),\n            }\n        )\n\n    paired_analysis = build_paired_turn8_analysis(pair_records)\n    standard_summary = summaries["STANDARD"]\n    exploratory_summary = summaries["EXPLORATORY"]\n    pair_assignment_rows = [\n        {\n            "pair_id": pair_id,\n            "standard_game_index": standard_index,\n            "environment_seed": environment_seed,\n            "search_seed": search_seed,\n        }\n        for pair_id, standard_index, environment_seed, search_seed in zip(\n            expected_pairs, expected_standard_indexes, expected_exploratory, expected_search, strict=True\n        )\n    ]\n    data: dict[str, Any] = {\n        "schema_version": "phase-c-pilot-aggregate-manifest-v2",\n        "implementation_commit": first.implementation_commit,\n        "implementation_tree": first.implementation_tree,\n        "activation_commit": first.activation_commit,\n        "locked_config_sha256": first.locked_config_sha256,\n        "workflow_sha256": first.workflow_sha256,\n        "approval_record_sha256": first.approval_record_sha256,\n        "standard_game_count": len(expected_standard),\n        "exploratory_game_count": len(expected_exploratory),\n        "standard_seed_sha256": _digest(expected_standard),\n        "exploratory_seed_sha256": _digest(expected_exploratory),\n        "exploratory_search_seed_sha256": _digest(expected_search),\n        "pair_assignment_sha256": _digest(pair_assignment_rows),\n        "paired_game_count": PAIRED_GAME_COUNT,\n        "paired_analysis_sha256": _digest(paired_analysis),\n        "standard_shard_count": expected_standard_shards,\n        "exploratory_shard_count": expected_exploratory_shards,\n        "standard_summary_sha256": _digest(standard_summary),\n        "exploratory_summary_sha256": _digest(exploratory_summary),\n        "shard_manifest_sha256s": tuple(sorted(all_manifest_shas)),\n        "pilot_authorized": True,\n        "aggregation_sha256": "",\n    }\n    data["aggregation_sha256"] = _digest(\n        {key: value for key, value in data.items() if key != "aggregation_sha256"}\n    )\n    return PhaseCAggregateManifest(**data), standard_summary, exploratory_summary, paired_analysis\n\n\n'''
replace_between(
    "src/mtg_runs/phase_c_artifacts.py",
    "def validate_phase_c_aggregate(\n",
    "def write_phase_c_aggregate(\n",
    aggregate_replacement,
)
write_aggregate = '''def write_phase_c_aggregate(\n    root: Path,\n    manifest: PhaseCAggregateManifest,\n    standard_summary: Mapping[str, Any],\n    exploratory_summary: Mapping[str, Any],\n    paired_analysis: Mapping[str, Any],\n) -> Path:\n    output = root / "aggregate"\n    output.mkdir(parents=True, exist_ok=False)\n    manifest_path = output / "manifest.json"\n    standard_path = output / "standard-summary.json"\n    exploratory_path = output / "exploratory-summary.json"\n    paired_path = output / "paired-turn8-analysis.json"\n    if _digest(standard_summary) != manifest.standard_summary_sha256:\n        raise ValueError("standard summary digest differs from aggregate manifest")\n    if _digest(exploratory_summary) != manifest.exploratory_summary_sha256:\n        raise ValueError("exploratory summary digest differs from aggregate manifest")\n    if _digest(paired_analysis) != manifest.paired_analysis_sha256:\n        raise ValueError("paired analysis digest differs from aggregate manifest")\n    manifest_path.write_bytes(_canonical(manifest.to_dict()) + b"\\n")\n    standard_path.write_bytes(_canonical(standard_summary) + b"\\n")\n    exploratory_path.write_bytes(_canonical(exploratory_summary) + b"\\n")\n    paired_path.write_bytes(_canonical(paired_analysis) + b"\\n")\n    for path in (manifest_path, standard_path, exploratory_path, paired_path):\n        path.chmod(0o444)\n    output.chmod(0o555)\n    return output\n\n\n'''
replace_between(
    "src/mtg_runs/phase_c_artifacts.py",
    "def write_phase_c_aggregate(\n",
    "__all__ = [\n",
    write_aggregate,
)

# ---------------------------------------------------------------------------
# Tests: rewrite the artifact test module around the paired contract and patch
# focused control tests.
# ---------------------------------------------------------------------------
artifact_tests = '''from __future__ import annotations\n\nimport json\nfrom dataclasses import asdict, replace\nfrom pathlib import Path\n\nimport pytest\n\nfrom mtg_measure import GameMeasurement, OpeningHandMeasurement, aggregate_measurements\nfrom mtg_runs.phase_c_artifacts import (\n    build_shard_manifest,\n    load_phase_c_shard,\n    make_game_artifact,\n    validate_phase_c_aggregate,\n    write_phase_c_shard,\n)\n\n\n@pytest.fixture(autouse=True)\ndef _restore_artifact_permissions(tmp_path: Path):\n    yield\n    for path in sorted(tmp_path.rglob("*"), key=lambda value: len(value.parts), reverse=True):\n        try:\n            path.chmod(0o755 if path.is_dir() else 0o644)\n        except FileNotFoundError:\n            pass\n    tmp_path.chmod(0o755)\n\n\ndef _measurement(\n    index: int,\n    seed: int,\n    mode: str,\n    *,\n    access8: bool = False,\n    pair_id: str | None = None,\n    paired_standard_game_index: int | None = None,\n    search_seed: int | None = None,\n    initial_hash: str | None = None,\n) -> GameMeasurement:\n    checkpoint = {5: False, 6: False, 8: access8, 10: access8}\n    failures = {\n        turn: (() if checkpoint[turn] else ("other_documented_cause",))\n        for turn in (5, 6, 8, 10)\n    }\n    primary = {turn: (None if not labels else labels[0]) for turn, labels in failures.items()}\n    return GameMeasurement(\n        schema_version="phase-b-game-measurement-v1",\n        game_index=index,\n        seed=seed,\n        mode=mode,\n        policy_config_id="anchor_balanced",\n        opening_hands=(OpeningHandMeasurement(1, 7, ("Island",) * 7, True),),\n        kept_at=7,\n        checkpoint_table_win_access=checkpoint,\n        failure_labels=failures,\n        primary_failure=primary,\n        combo_records=(),\n        earliest_legal_attempt_turn=None,\n        actual_first_attempt_turn=None,\n        attempt_package=None,\n        attempt_timing=None,\n        usable_protection_count=0,\n        protection_in_hand_not_payable=False,\n        protection_category_mismatch=False,\n        independent_second_line_available=False,\n        card_records=(),\n        extra={\n            "environment_seed": seed,\n            "environment_initial_state_hash": initial_hash or f"{seed + 2:064x}"[-64:],\n            "search_seed": search_seed,\n            "pair_id": pair_id,\n            "paired_standard_game_index": paired_standard_game_index,\n        },\n    )\n\n\ndef _write_shard(\n    root: Path,\n    *,\n    mode: str,\n    shard_index: int,\n    shard_count: int,\n    first_index: int,\n    seeds: tuple[int, ...],\n    pair_ids: tuple[str | None, ...] | None = None,\n    paired_standard_indexes: tuple[int | None, ...] | None = None,\n    search_seeds: tuple[int | None, ...] | None = None,\n    access8: tuple[bool, ...] | None = None,\n) -> Path:\n    pair_ids = pair_ids or (None,) * len(seeds)\n    paired_standard_indexes = paired_standard_indexes or (None,) * len(seeds)\n    search_seeds = search_seeds or (None,) * len(seeds)\n    access8 = access8 or (False,) * len(seeds)\n    initial_hashes = tuple(f"{seed + 2:064x}"[-64:] for seed in seeds)\n    measurements = tuple(\n        _measurement(\n            first_index + offset,\n            seed,\n            mode,\n            access8=access8[offset],\n            pair_id=pair_ids[offset],\n            paired_standard_game_index=paired_standard_indexes[offset],\n            search_seed=search_seeds[offset],\n            initial_hash=initial_hashes[offset],\n        )\n        for offset, seed in enumerate(seeds)\n    )\n    replays = tuple(\n        {"schema_version": "test-replay-v1", "seed": seed, "digest": f"{seed:064x}"[-64:]}\n        for seed in seeds\n    )\n    technical = tuple(\n        {\n            "schema_version": "phase-c-technical-game-v2",\n            "mode": mode,\n            "seed": seed,\n            "environment_initial_state_hash": initial_hashes[offset],\n            "search_seed": search_seeds[offset],\n            "pair_id": pair_ids[offset],\n            "paired_standard_game_index": paired_standard_indexes[offset],\n            "replay_digest": replay["digest"],\n            "final_state_hash": f"{seed + 1:064x}"[-64:],\n            "terminal_status": "ACTIVE",\n        }\n        for offset, (seed, replay) in enumerate(zip(seeds, replays, strict=True))\n    )\n    games = tuple(\n        make_game_artifact(\n            mode=mode,\n            game_index=measurement.game_index,\n            seed=seed,\n            technical_game=game,\n            replay=replay,\n            measurement=measurement,\n        )\n        for seed, game, replay, measurement in zip(\n            seeds, technical, replays, measurements, strict=True\n        )\n    )\n    summary = asdict(aggregate_measurements(measurements))\n    manifest = build_shard_manifest(\n        mode=mode,\n        shard_index=shard_index,\n        shard_count=shard_count,\n        first_game_index=first_index,\n        seeds=seeds,\n        pair_ids=pair_ids,\n        paired_standard_game_indexes=paired_standard_indexes,\n        search_seeds=search_seeds,\n        implementation_commit="1" * 40,\n        implementation_tree="2" * 40,\n        activation_commit="3" * 40,\n        locked_config_sha256="4" * 64,\n        workflow_sha256="5" * 64,\n        approval_record_sha256="6" * 64,\n        policy_config_id="anchor_balanced",\n        policy_config_sha256="7" * 64,\n        evaluator_snapshot_id="contextual_combo_v1",\n        evaluator_snapshot_sha256="8" * 64,\n        learning_plan_sha256="9" * 64,\n        technical_games=technical,\n        game_records=games,\n        replays=replays,\n        measurements=measurements,\n        summary=summary,\n    )\n    return write_phase_c_shard(root, manifest, technical, games, replays, measurements, summary)\n\n\ndef test_manifest_rejects_git_oid_and_sha256_domain_mixing(tmp_path: Path) -> None:\n    measurement = _measurement(1, 11, "STANDARD")\n    replay = {"digest": "a" * 64}\n    technical = {\n        "seed": 11,\n        "pair_id": None,\n        "paired_standard_game_index": None,\n        "search_seed": None,\n        "replay_digest": "a" * 64,\n        "final_state_hash": "b" * 64,\n        "terminal_status": "ACTIVE",\n    }\n    game = make_game_artifact(\n        mode="STANDARD", game_index=1, seed=11, technical_game=technical, replay=replay, measurement=measurement\n    )\n    summary = asdict(aggregate_measurements((measurement,)))\n    with pytest.raises(ValueError, match="40-character Git object ID"):\n        build_shard_manifest(\n            mode="STANDARD", shard_index=0, shard_count=1, first_game_index=1, seeds=(11,),\n            pair_ids=(None,), paired_standard_game_indexes=(None,), search_seeds=(None,),\n            implementation_commit="1" * 64, implementation_tree="2" * 40, activation_commit="3" * 40,\n            locked_config_sha256="4" * 64, workflow_sha256="5" * 64, approval_record_sha256="6" * 64,\n            policy_config_id="anchor_balanced", policy_config_sha256="7" * 64,\n            evaluator_snapshot_id="contextual_combo_v1", evaluator_snapshot_sha256="8" * 64,\n            learning_plan_sha256="9" * 64, technical_games=(technical,), game_records=(game,),\n            replays=(replay,), measurements=(measurement,), summary=summary,\n        )\n\n\ndef test_shard_cross_file_tampering_fails_closed(tmp_path: Path) -> None:\n    root = tmp_path / "technical"\n    root.mkdir()\n    shard = _write_shard(root, mode="STANDARD", shard_index=0, shard_count=1, first_index=1, seeds=(11,))\n    technical_path = shard / "technical-games.jsonl"\n    technical = json.loads(technical_path.read_text().strip())\n    technical["final_state_hash"] = "f" * 64\n    technical_path.chmod(0o644)\n    technical_path.write_text(json.dumps(technical) + "\\n")\n    with pytest.raises(ValueError, match="technical-game digest differs"):\n        load_phase_c_shard(shard)\n\n\ndef test_exact_500_200_paired_aggregation_is_deterministic_and_reports_real_pairs(tmp_path: Path) -> None:\n    standard = tuple(range(1, 501))\n    paired_indexes = tuple(shard * 50 + offset + 1 for shard in range(10) for offset in range(20))\n    exploratory = tuple(standard[index - 1] for index in paired_indexes)\n    search = tuple(range(10_001, 10_201))\n    pair_ids = tuple(f"{index:024x}"[-24:] for index in range(1, 201))\n    pair_ordinal_by_standard = {standard_index: ordinal for ordinal, standard_index in enumerate(paired_indexes)}\n    shard_dirs: list[Path] = []\n    for shard_index in range(10):\n        standard_start = shard_index * 50\n        standard_indexes = tuple(range(standard_start + 1, standard_start + 51))\n        standard_pair_ids = tuple(\n            pair_ids[pair_ordinal_by_standard[index]] if index in pair_ordinal_by_standard else None\n            for index in standard_indexes\n        )\n        standard_pair_indexes = tuple(index if index in pair_ordinal_by_standard else None for index in standard_indexes)\n        standard_access = tuple(\n            (pair_ordinal_by_standard[index] % 4 in {0, 1}) if index in pair_ordinal_by_standard else False\n            for index in standard_indexes\n        )\n        shard_dirs.append(\n            _write_shard(\n                tmp_path, mode="STANDARD", shard_index=shard_index, shard_count=10,\n                first_index=standard_start + 1, seeds=standard[standard_start:standard_start + 50],\n                pair_ids=standard_pair_ids, paired_standard_indexes=standard_pair_indexes,\n                search_seeds=(None,) * 50, access8=standard_access,\n            )\n        )\n        exploratory_start = shard_index * 20\n        ordinals = range(exploratory_start, exploratory_start + 20)\n        shard_dirs.append(\n            _write_shard(\n                tmp_path, mode="EXPLORATORY", shard_index=shard_index, shard_count=10,\n                first_index=exploratory_start + 1, seeds=exploratory[exploratory_start:exploratory_start + 20],\n                pair_ids=pair_ids[exploratory_start:exploratory_start + 20],\n                paired_standard_indexes=paired_indexes[exploratory_start:exploratory_start + 20],\n                search_seeds=search[exploratory_start:exploratory_start + 20],\n                access8=tuple(ordinal % 4 in {0, 2} for ordinal in ordinals),\n            )\n        )\n    first, standard_summary, exploratory_summary, paired = validate_phase_c_aggregate(\n        shard_dirs, expected_standard_seeds=standard, expected_exploratory_seeds=exploratory,\n        expected_exploratory_search_seeds=search, expected_pair_ids=pair_ids,\n        expected_paired_standard_game_indexes=paired_indexes, expected_standard_shards=10,\n        expected_exploratory_shards=10,\n    )\n    second, _, _, paired_second = validate_phase_c_aggregate(\n        tuple(reversed(shard_dirs)), expected_standard_seeds=standard, expected_exploratory_seeds=exploratory,\n        expected_exploratory_search_seeds=search, expected_pair_ids=pair_ids,\n        expected_paired_standard_game_indexes=paired_indexes, expected_standard_shards=10,\n        expected_exploratory_shards=10,\n    )\n    assert first == second\n    assert paired == paired_second\n    assert standard_summary["game_denominator"] == 500\n    assert exploratory_summary["game_denominator"] == 200\n    assert paired["pair_count"] == 200\n    assert paired["both_access"] == 50\n    assert paired["standard_only_access"] == 50\n    assert paired["exploratory_only_access"] == 50\n    assert paired["neither_access"] == 50\n    assert paired["paired_access_rate_difference"] == 0.0\n    assert paired["mcnemar_exact_two_sided_p_value"] == 1.0\n    assert paired["paired_access_rate_difference_ci"]["lower"] <= 0.0\n    assert paired["paired_access_rate_difference_ci"]["upper"] >= 0.0\n\n\ndef test_pairing_tamper_fails_closed(tmp_path: Path) -> None:\n    pair_id = "a" * 24\n    standard = _write_shard(\n        tmp_path, mode="STANDARD", shard_index=0, shard_count=1, first_index=1, seeds=(11,),\n        pair_ids=(pair_id,), paired_standard_indexes=(1,), search_seeds=(None,),\n    )\n    measurement_path = standard / "measurements.jsonl"\n    payload = json.loads(measurement_path.read_text().strip())\n    payload["extra"]["pair_id"] = "b" * 24\n    measurement_path.chmod(0o644)\n    measurement_path.write_text(json.dumps(payload) + "\\n")\n    with pytest.raises(ValueError, match="pair ID linkage"):\n        load_phase_c_shard(standard)\n'''
(ROOT / "tests/phase_c/test_phase_c_artifacts.py").write_text(artifact_tests, encoding="utf-8")

replace_once(
    "tests/phase_c/test_phase_c_control.py",
    "    build_pilot_seed_plan,\n",
    "    build_pilot_seed_plan,\n    build_pilot_shard_assignment,\n",
)
replace_once(
    "tests/phase_c/test_phase_c_control.py",
    "    run_phase_c_exploratory_smoke,\n",
    "    run_phase_c_exploratory_smoke,\n    run_phase_c_paired_environment_smoke,\n",
)
replace_between(
    "tests/phase_c/test_phase_c_control.py",
    "def test_seed_plan_is_deterministic_exact_and_disjoint() -> None:\n",
    "\n\ndef test_dry_run_derives_readiness_from_real_smokes_and_creates_no_result()",
    '''def test_seed_plan_is_deterministic_exact_and_paired() -> None:\n    config = load_phase_c_config()\n    first = build_pilot_seed_plan(config)\n    second = build_pilot_seed_plan(config)\n    assert first == second\n    assert len(first.standard) == 500\n    assert len(first.exploratory) == 200\n    assert set(first.exploratory).issubset(first.standard)\n    assert len(first.exploratory_search) == 200\n    assert not set(first.exploratory_search).intersection(first.standard)\n    assert len(set(first.pair_ids)) == 200\n    assert len(first.paired_standard_game_indexes) == 200\n    for shard_index in range(10):\n        standard_assignment = build_pilot_shard_assignment(\n            config, first, mode="STANDARD", shard_index=shard_index\n        )\n        exploratory_assignment = build_pilot_shard_assignment(\n            config, first, mode="EXPLORATORY", shard_index=shard_index\n        )\n        assert len([value for value in standard_assignment.pair_ids if value is not None]) == 20\n        assert exploratory_assignment.seeds == tuple(\n            seed for seed, pair_id in zip(standard_assignment.seeds, standard_assignment.pair_ids, strict=True)\n            if pair_id is not None\n        )\n        assert all(value is not None for value in exploratory_assignment.search_seeds)\n\n\ndef test_paired_modes_share_environment_but_not_search_rng() -> None:\n    smoke = run_phase_c_paired_environment_smoke(environment_seed=505, search_seed=606)\n    assert smoke["status"] == "PASS"\n    assert smoke["opening_environment_equal"] is True\n    assert smoke["standard_search_seed"] is None\n    assert smoke["exploratory_search_seed"] == 606\n''',
)
replace_once(
    "tests/phase_c/test_phase_c_control.py",
    "        \"EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED\",\n"
    "        \"COMBO_ACCESS_DETECTORS_INCOMPLETE\",\n",
    "        \"EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED\",\n"
    "        \"PAIRED_EXPLORATORY_DESIGN_NOT_IMPLEMENTED\",\n"
    "        \"COMBO_ACCESS_DETECTORS_INCOMPLETE\",\n",
)
replace_once(
    "tests/phase_c/test_phase_c_control.py",
    "    assert report.exploratory_production_decision_layer_depth == 1\n",
    "    assert report.exploratory_production_decision_layer_depth == 1\n"
    "    assert report.paired_game_count == 200\n"
    "    assert report.exploratory_search_seed_sha256 != report.exploratory_seed_sha256\n",
)

# Reporting-language and analysis preregistration: append to the human contract.
auth_path = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md"
auth_text = auth_path.read_text(encoding="utf-8")
appendix = '''\n\n## Pre-registered metric language and paired exploratory comparison\n\nThe pilot measures **legal deterministic table-win access under a no-interaction opponent model**. Findings must be described as "table-win access by Turn N" or "combo access by Turn N" and must not be described as win rate, wins by Turn N, or real-table performance. Every results summary must include: *These figures measure combo assembly speed against opponents who take no actions. They are not win rates and do not predict performance against interactive opponents.*\n\nThe 200 exploratory executions are not an independent draw sample. They reuse a frozen 200-game subset of the 500 standard **environment seeds**, exactly 20 from each 50-game standard shard. STANDARD and EXPLORATORY runs for a pair initialize from the same environment seed. Exploratory search randomness is derived from a separate frozen search-seed namespace and never perturbs environment RNG.\n\nThe primary exploratory comparison is paired Turn-8 table-win access. The aggregate reports BOTH_ACCESS, STANDARD_ONLY_ACCESS, EXPLORATORY_ONLY_ACCESS, and NEITHER_ACCESS; the paired access-rate difference `(EXPLORATORY_ONLY - STANDARD_ONLY) / 200`; a two-sided exact McNemar test on discordant pairs; and a 95% deterministic paired-bootstrap percentile interval using 10,000 pre-registered resamples. First-decision divergence, branch count, node count, and actual one-layer depth are secondary diagnostics. A null paired effect is not evidence that the baseline is optimal.\n'''
if "## Pre-registered metric language and paired exploratory comparison" not in auth_text:
    auth_path.write_text(auth_text.rstrip() + appendix + "\n", encoding="utf-8")

print("paired redesign transformations applied")
