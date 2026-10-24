"""C01 — collect persisted observations; never accept evidence from the browser."""
from datetime import date, timedelta


def observe(db, tenant, customer):
    start = (date.today() - timedelta(days=13)).isoformat()
    rows = db.execute('SELECT id,day,value,source FROM observations WHERE tenant=? AND customer=? AND day>=? AND day<=? ORDER BY day', (tenant, customer, start, date.today().isoformat())).fetchall()
    expected = [(date.today() - timedelta(days=13-i)).isoformat() for i in range(14)]
    enough = [r['day'] for r in rows] == expected and all(isinstance(r['value'], int) and r['value'] >= 0 for r in rows) and len({r['source'] for r in rows}) == 1
    return {'sufficient': enough, 'rows': [dict(r) for r in rows], 'metric': 'resultados de negócio concluídos por dia', 'window': '7 dias anteriores vs. 7 dias recentes', 'rule': 'queda >= 30%; 14 dias completos, mesma fonte; baseline > 0'}
