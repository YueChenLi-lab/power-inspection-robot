"""All mission state changes must pass this graph, including recovery."""
from enum import Enum


class State(str, Enum):
    CREATED = 'CREATED'
    VALIDATING = 'VALIDATING'
    WAITING_APPROVAL = 'WAITING_APPROVAL'
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    RETRY_WAIT = 'RETRY_WAIT'
    WAITING_NETWORK = 'WAITING_NETWORK'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'


TERMINAL = {State.SUCCEEDED, State.FAILED, State.CANCELLED}
TRANSITIONS = {
    State.CREATED: {State.VALIDATING, State.CANCELLED},
    State.VALIDATING: {State.WAITING_APPROVAL, State.QUEUED, State.FAILED, State.CANCELLED},
    State.WAITING_APPROVAL: {State.QUEUED, State.FAILED, State.CANCELLED},
    State.QUEUED: {State.RUNNING, State.WAITING_NETWORK, State.WAITING_APPROVAL, State.FAILED, State.CANCELLED},
    State.RUNNING: {State.SUCCEEDED, State.FAILED, State.RETRY_WAIT, State.WAITING_APPROVAL, State.CANCELLED},
    State.RETRY_WAIT: {State.QUEUED, State.FAILED, State.CANCELLED},
    State.WAITING_NETWORK: {State.QUEUED, State.FAILED, State.CANCELLED},
}


def validate_transition(before, after):
    if State(after) not in TRANSITIONS.get(State(before), set()):
        raise ValueError(f'illegal transition: {before} -> {after}')
