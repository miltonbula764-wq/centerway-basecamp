"""C05 — bounded sandbox effects. Called only inside Core's write transaction."""
from copy import deepcopy


def intervene(action, state):
    result = deepcopy(state)
    if action == 'resume_connector' and result.get('connector') == 'paused':
        result['connector'] = 'active'
        delivered = 0
        for job in result['backlog']:
            if job['status'] == 'pending':
                job['status'] = 'delivered'
                delivered += 1
        result['completed_outcomes'] += delivered
    elif action == 'enable_workflow' and result.get('workflow_enabled') is False:
        result['workflow_enabled'] = True
    else:
        raise ValueError('Precondição da intervenção deixou de ser válida.')
    return result
