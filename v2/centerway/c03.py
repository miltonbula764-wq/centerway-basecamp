"""C03 — investigate the test system and preserve a revision-bound snapshot."""
import hashlib
from .store import encode


def investigate(environment, observation, detection):
    state = environment['state']
    cause = 'connector_paused' if state.get('connector') == 'paused' else 'workflow_disabled' if state.get('workflow_enabled') is False else 'unknown'
    evidence = {'state': state, 'revision': environment['revision'], 'observation_ids': detection['evidence_ids'], 'metric': observation['metric'], 'cause': cause}
    return {**evidence, 'sha256': hashlib.sha256(encode(evidence).encode()).hexdigest()}
