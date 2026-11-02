"""One retry policy for live failures and restart recovery.

Idempotence is a declared contract, not proof about unknown external effects.
Unknown results additionally require an explicit recovery-safe Mock declaration.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryDecision:
    allowed: bool
    needs_review: bool
    reason: str


def retry_decision(spec, mission, safety, *, result_uncertain=True) -> RetryDecision:
    def no(reason, review=False):
        return RetryDecision(False, review, reason)

    if mission['status'] not in ('RUNNING','RETRY_WAIT'):
        return no('state_does_not_allow_retry')
    if spec is None:
        return no('skill_unavailable')
    if spec.version != mission['skill_version']:
        return no('skill_version_changed')
    decision = safety.decision(spec, approved=mission['approved'] == 1)
    if decision != 'ALLOW':
        return no('unresolved_safety_approval', review=decision == 'APPROVAL')
    if spec.requires_network_authorization and mission['approved'] != 1:
        return no('unresolved_network_authorization', review=True)
    if spec.idempotent is not True:
        return no('non_idempotent_result_uncertain', review=result_uncertain)
    if spec.retryable is not True:
        return no('skill_disallows_retry')
    if mission['attempts'] >= mission['max_attempts']:
        return no('attempt_budget_exhausted')
    if result_uncertain and not (spec.execution_scope == 'mock' and spec.recovery_safe is True):
        return no('unknown_effects_require_review', review=True)
    return RetryDecision(True, False, 'retry_contract_satisfied')
