"""C02 — a candidate signal is not authorization to execute."""

def detect(observation):
    if not observation['sufficient']:
        return {'status': 'insufficient_data', 'reason': 'São necessários 14 dias completos e comparáveis.'}
    rows = observation['rows']
    baseline = sum(r['value'] for r in rows[:7])
    recent = sum(r['value'] for r in rows[7:])
    if baseline <= 0:
        return {'status': 'insufficient_data', 'reason': 'Baseline sem resultados; impossível calcular deterioração.'}
    drop = round(1 - recent / baseline, 4)
    return {'status': 'deteriorating' if drop >= .30 else 'healthy', 'baseline': baseline, 'recent': recent, 'drop': drop, 'evidence_ids': [r['id'] for r in rows]}
