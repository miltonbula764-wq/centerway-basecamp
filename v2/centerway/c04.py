"""C04 — explicitly simulated decisions, constrained to an authorized catalogue."""
CATALOGUE = {
    'resume_connector': {'label': 'Retomar conector e reprocessar fila', 'tenant': 'atlas', 'cause': 'connector_paused', 'permission': 'operator', 'effect': 'Ativa o conector e entrega os trabalhos pendentes no sandbox.'},
    'enable_workflow': {'label': 'Ativar percurso de primeiro valor', 'tenant': 'nimbus', 'cause': 'workflow_disabled', 'permission': 'operator', 'effect': 'Ativa o percurso; não inventa resultados de utilização.'},
}
MODE = 'simulator-v1'


def decide(tenant, investigation):
    candidates = [key for key, action in CATALOGUE.items() if action['tenant'] == tenant and action['cause'] == investigation['cause']]
    return {'mode': MODE, 'is_real_ai': False, 'action': candidates[0] if candidates else None, 'classification': investigation['cause'], 'reason': f"Simulador determinístico: causa {investigation['cause']}, evidências persistidas {investigation['observation_ids']}, revisão {investigation['revision']}.", 'evidence_hash': investigation['sha256']}
