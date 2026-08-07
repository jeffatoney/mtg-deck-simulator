from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/phase-c-pilot.yml"


def test_phase_c_workflow_propagates_external_identity_anchor_to_every_job() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    anchor = "IDENTITY_MODEL_SHA256: ${{ vars.IDENTITY_MODEL_V2_SHA256 }}"
    assert text.count(anchor) == 3


def test_phase_c_workflow_binds_the_definition_github_actually_executes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "- name: Bind executed workflow definition" in text
    assert "RUNTIME_WORKFLOW_COMMIT: ${{ github.workflow_sha }}" in text
    assert (
        'git cat-file blob "${RUNTIME_WORKFLOW_COMMIT}:.github/workflows/phase-c-pilot.yml"'
        in text
    )
    assert 'test "${RUNTIME_WORKFLOW_SHA256}" = "${WORKFLOW_SHA256}"' in text
    assert 'test "${CHECKED_OUT_WORKFLOW_SHA256}" = "${WORKFLOW_SHA256}"' in text


def test_preflight_only_uses_no_approval_or_activation_and_never_executes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "preflight_only:" in text
    assert "type: boolean" in text
    assert "default: false" in text
    assert (
        "confirmation:\n"
        "        description: Exact Phase C owner confirmation token; required for execution, ignored when preflight_only is true\n"
        "        required: false\n"
        '        default: ""'
    ) in text
    assert (
        "activation_commit:\n"
        "        description: Exact governance-only owner activation commit; required for execution, ignored when preflight_only is true\n"
        "        required: false\n"
        '        default: ""'
    ) in text
    assert (
        "ref: ${{ inputs.preflight_only && inputs.implementation_commit || inputs.activation_commit }}"
        in text
    )
    assert "- name: Validate locked preflight-only bindings" in text
    assert "if: ${{ inputs.preflight_only }}" in text
    assert "- name: Validate implementation and governance-only activation" in text
    assert text.count("if: ${{ !inputs.preflight_only }}") >= 2
    assert "if: ${{ !inputs.preflight_only && needs.shards.result == 'success' }}" in text
