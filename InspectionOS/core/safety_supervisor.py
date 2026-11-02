"""Execution policy uses trusted registry metadata, never a model's risk claims."""
import hmac


class SafetySupervisor:
    def __init__(self, operator_token=None): self._operator_token = operator_token

    def decision(self, spec, approved=False):
        if spec.execution_scope != 'mock' or spec.risk_level == 'motion':
            return 'DENY'
        if spec.risk_level == 'high' and not approved: return 'APPROVAL'
        return 'ALLOW'

    def authenticate_operator(self, actor, token):
        if not actor or not isinstance(token,str) or not self._operator_token or not hmac.compare_digest(token,self._operator_token):
            raise PermissionError('independent local operator credential required')
