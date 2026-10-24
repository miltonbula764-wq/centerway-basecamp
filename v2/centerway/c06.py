"""C06 — independent post-write read and explicit business-value threshold."""
from .store import now


def verify(state, before):
    if 'connector' in state:
        operational = state['connector'] == 'active' and all(j['status'] == 'delivered' for j in state['backlog'])
        probe = 'Conector ativo e zero trabalhos pendentes.'
    else:
        operational = state.get('workflow_enabled') is True
        probe = 'Percurso de primeiro valor disponível.'
    gained = state['completed_outcomes'] - before['completed_outcomes']
    return {'operational_recovered': operational, 'value_recovered': operational and gained >= 4, 'outcomes_before': before['completed_outcomes'], 'outcomes_after': state['completed_outcomes'], 'gained': gained, 'value_target': 4, 'probe': probe, 'measured_at': now(), 'scope': 'sandbox', 'reason': 'Recuperação de valor exige pelo menos 4 novos resultados persistidos; disponibilidade técnica por si só não prova valor.'}
