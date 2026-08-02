from __future__ import annotations

from dataclasses import replace
import pytest
from mtg_kernel.strategic_choices import PublicCard
from mtg_policy.evaluation import ContextualEvaluator, declared_effect_kinds, load_evaluator_config, load_learned_evaluator_config
from mtg_policy.learning import ActionSignature, CounterfactualContract, DecisionContext, LearningPlan, OutcomeVector, PairwiseTrainingExample, VisibleCardRecord, load_learning_dataset, load_learning_plan, train_evaluator_snapshot, write_learning_dataset, write_snapshot


def observation(*, turn:int, lands:int)->dict[str,object]:
    objects=[{"handle":f"land-{i}","zone":"BATTLEFIELD","owner":"P0","controller":"P0","identity":"Island","face_down":False,"card_types":["Land"]} for i in range(lands)]
    return {"player":"P0","objects":objects,"turn":{"number":turn},"mana_pool":{"U":0,"R":0,"C":0}}

def card(handle:str,name:str,*,land:bool=False,effects:tuple[str,...]=())->PublicCard:
    return PublicCard(handle,name,0 if land else 2,("Land",) if land else ("Sorcery",),effects)

def _outcome(win:bool,*,turn:int=3)->OutcomeVector:
    return OutcomeVector(int(win),int(win),int(win),0,-turn if win else -10,-turn if win else -10,(int(win),)*4,turn if win else None,turn if win else None)

def _compact_plan(discovery_count:int,validation_count:int,*,schema:tuple[str,...]=("combo_completion","excess_land"),raw:bool=False,mining_seed_count:int=5,confirmation_seed_count:int=5)->LearningPlan:
    return LearningPlan("p"*64,"pairwise-ridge-ranking-v2",discovery_count,validation_count,1.0,0.0,2,5,schema,discovery_count,validation_count,1,1,mining_seed_count,confirmation_seed_count,0.03,1.96,True,True,raw,4,4,2,2,10)

def _contract(seed:int)->CounterfactualContract:
    digest=f"{seed:064x}"[-64:]; return CounterfactualContract(digest,digest,"continuation-v1","c"*64)

def _context(index:int)->DecisionContext:
    return DecisionContext(index,3,"PRECOMBAT_MAIN",(VisibleCardRecord("Dualcaster Mage","HAND",("Creature",)),VisibleCardRecord("Twinflame","REVEALED",("Sorcery",))),(ActionSignature("CAST","Twinflame"),ActionSignature("SELECT_PILE","three Islands")),(ActionSignature("CAST","Opt"),),( ("R",3),("U",1)),3,1,("dualcaster_twinflame",))

def _rich_example(example_id:str,seed:int,index:int=1)->PairwiseTrainingExample:
    return PairwiseTrainingExample(example_id,seed,"PILE",{"combo_completion":1.0,"excess_land":0.0},{"combo_completion":0.0,"excess_land":2.0},_outcome(True),_outcome(False),index,_context(index),ActionSignature("SELECT_PILE","Twinflame pile"),ActionSignature("SELECT_PILE","Island pile"),("Dualcaster Mage","Twinflame"),("Island","Mountain"),_contract(seed))

def test_evaluator_classifies_every_exact_deck_effect_and_fails_closed()->None:
    config=load_evaluator_config(); assert set(config.effect_features)==set(declared_effect_kinds()); evaluator=ContextualEvaluator(config)
    with pytest.raises(ValueError,match="unclassified strategic effect"): evaluator.evaluate_pile((card("unknown","Unknown",effects=("NOT_CLASSIFIED",)),),observation(turn=3,lands=3))

def test_on_curve_flood_pile_loses_to_missing_twinflame()->None:
    evaluator=ContextualEvaluator(load_evaluator_config()); flood=tuple(card(f"i{i}","Island",land=True,effects=("ADD_MANA",)) for i in range(3)); combo=(card("m","Mountain",land=True,effects=("ADD_MANA",)),card("t","Twinflame",effects=("CREATE_TOKEN_COPIES",)))
    current=observation(turn=3,lands=3); current["objects"]=[*current["objects"],{"handle":"dual","zone":"HAND","owner":None,"controller":None,"identity":"Dualcaster Mage","face_down":False,"card_types":["Creature"]}]
    flood_eval=evaluator.evaluate_pile(flood,current); combo_eval=evaluator.evaluate_pile(combo,current); assert combo_eval.score>flood_eval.score and "dualcaster_twinflame" in combo_eval.completed_packages

def test_discovery_learning_uses_relative_three_point_gate_and_outcome_guardrails()->None:
    snapshot=train_evaluator_snapshot(parent_evaluator_id="contextual_combo_v1",parent_evaluator_sha256="e"*64,discovery=tuple(_rich_example(f"d-{i}",i) for i in range(10)),validation=tuple(_rich_example(f"v-{i}",100+i) for i in range(4)),plan=_compact_plan(10,4),baseline_weights={"combo_completion":0.0,"excess_land":0.0},enforce_plan_counts=False)
    assert snapshot.status=="FROZEN_VALIDATED" and snapshot.learned_validation_accuracy==1.0 and snapshot.validation_accuracy_improvement>=0.03 and snapshot.clustered_ci_lower>0 and snapshot.outcome_guardrails.passed

def test_learning_rejects_discovery_validation_seed_overlap()->None:
    example=_rich_example("same",1)
    with pytest.raises(ValueError,match="seeds overlap"): train_evaluator_snapshot(parent_evaluator_id="contextual_combo_v1",parent_evaluator_sha256="e"*64,discovery=(example,),validation=(replace(example,example_id="different"),),plan=_compact_plan(1,1,mining_seed_count=1,confirmation_seed_count=0),enforce_plan_counts=False)

def test_learning_surfaces_review_only_card_pair_and_action_sequence_candidates()->None:
    snapshot=train_evaluator_snapshot(parent_evaluator_id="contextual_combo_v1",parent_evaluator_sha256="e"*64,discovery=tuple(_rich_example(f"pair-{i}",i) for i in range(10)),validation=tuple(_rich_example(f"holdout-{i}",100+i) for i in range(4)),plan=_compact_plan(10,4,raw=True),baseline_weights={"combo_completion":0.0,"excess_land":0.0},enforce_plan_counts=False)
    candidates=snapshot.organic_interaction_candidates
    assert any(i.candidate_type=="CARD_PAIR" and i.members==("Dualcaster Mage","Twinflame") for i in candidates)
    assert any(i.candidate_type=="ACTION_SEQUENCE" for i in candidates) and all(i.status=="REVIEW_REQUIRED" and not i.auto_activation_allowed for i in candidates)

def test_raw_learning_dataset_is_canonical_hidden_information_safe_and_round_trips(tmp_path)->None:
    path=tmp_path/"dataset.json"; digest=write_learning_dataset((_rich_example("b",2),_rich_example("a",1)),path); loaded=load_learning_dataset(path); assert [i.example_id for i in loaded]==["a","b"] and digest==__import__("json").loads(path.read_text())["examples_sha256"]

def test_counterfactual_contract_rejects_nonidentical_rng()->None:
    with pytest.raises(ValueError,match="differ only"): CounterfactualContract("a"*64,"b"*64,"p","c"*64,same_future_rng_streams=False)

def test_frozen_plan_uses_equal_seed_quotas_and_review_only_mining()->None:
    plan=load_learning_plan(); assert (plan.discovery_example_count,plan.validation_example_count,plan.comparisons_per_discovery_seed,plan.comparisons_per_validation_seed,plan.mining_seed_count,plan.confirmation_seed_count)==(4800,1000,16,5,200,100) and plan.minimum_relative_accuracy_improvement==0.03

def test_content_addressed_learned_snapshot_can_be_selected_as_a_policy_button(tmp_path)->None:
    base=load_evaluator_config(); plan=load_learning_plan(); schema=plan.required_feature_schema
    def features(**values:float)->dict[str,float]: result={name:0.0 for name in schema}; result.update(values); return result
    discovery=tuple(replace(_rich_example(f"full-d-{i}",i),features_a=features(combo_completion=1.0),features_b=features(excess_land=2.0)) for i in range(10)); validation=tuple(replace(_rich_example(f"full-v-{i}",100+i),features_a=features(combo_completion=1.0),features_b=features(excess_land=1.0)) for i in range(4))
    compact=replace(plan,discovery_example_count=10,validation_example_count=4,mining_seed_count=5,confirmation_seed_count=5,feature_cross_candidate_min_support=2,organic_candidate_min_support=4,organic_candidate_min_distinct_seeds=4,organic_candidate_min_mining_support=2,organic_candidate_min_confirmation_support=2)
    snapshot=train_evaluator_snapshot(parent_evaluator_id=base.evaluator_id,parent_evaluator_sha256=base.config_sha256,discovery=discovery,validation=validation,plan=compact,baseline_weights={name:0.0 for name in schema},enforce_plan_counts=False); learned=load_learned_evaluator_config(write_snapshot(snapshot,tmp_path)); assert learned.evaluator_id==snapshot.snapshot_id and learned.weights["combo_completion"]>0

def test_canonical_policy_fails_closed_on_unadjudicated_dualcaster_twinflame_loop()->None:
    from mtg_kernel.errors import UnsupportedCapability
    from mtg_kernel.strategic_choices import SpellCopyTargetRequest
    from mtg_policy.choices import PolicyStrategicChoiceProvider
    from mtg_policy.config import load_policy_matrix
    provider=PolicyStrategicChoiceProvider(load_policy_matrix()[0],ContextualEvaluator(load_evaluator_config())); target=PublicCard("target","Dualcaster Mage",3,("Creature",),("CREATE_SPELL_COPY",))
    request=SpellCopyTargetRequest("loop","P0","Dualcaster Mage","Twinflame",3,observation(turn=3,lands=3),("target",),(target,),( ("target",),))
    with pytest.raises(UnsupportedCapability,match="loop adjudication is not implemented"): provider.choose_spell_copy_targets(request)
