"""Reproducible 150-client sandbox. Uses the same validated Core as HTTP."""
import argparse
from datetime import date, timedelta
from .core import Core, Problem
from .store import Store, encode

EXPECTED_COUNTS = {'observation':14, 'deterioration':16, 'investigation':14,
                   'intervention':35, 'recovery':23, 'exceptions':32, 'stable':16}


def sample_rows(baseline=10, recent=2, days=14, source='synthetic-v2'):
    return [{'day':(date.today()-timedelta(days=13-i)).isoformat(),
             'value':baseline if i<7 else recent, 'source':source} for i in range(days)]


def populate(store, actor='demo'):
    with store.transaction() as db:
        if db.execute('SELECT 1 FROM environments LIMIT 1').fetchone():
            raise Problem(409,'A base deve estar sem clientes. Não se alteram ensaios existentes.')
    core = Core(store)
    for tenant in ('atlas','nimbus'):
        for i in range(75):
            customer, group = f'client-{i+1:03}', i % 10
            core.create_customer(actor,tenant,customer,f'Cliente sintético {i+1:03}', 'operational' if group in (1,3) else 'blocked')
            core.ingest(actor,tenant,customer,sample_rows(recent=10 if group==1 else 2, days=3 if group==2 else 14))
            if group == 9:
                continue
            case_id = core.advance(actor,tenant,customer)['case_id']
            core.advance(actor,tenant,customer,case_id)
            if group in (1,2,4):
                continue
            core.advance(actor,tenant,customer,case_id)
            if group == 5:
                continue
            core.advance(actor,tenant,customer,case_id)
            if group in (3,6):
                continue
            core.execute(actor,tenant,customer,case_id)
            if group == 7:
                continue
            if tenant == 'nimbus' and group == 0:
                core.simulate_usage(actor,tenant,customer,case_id)
            core.verify(actor,tenant,customer,case_id)
    result = core.view(actor)
    assert len(result['registry']) == 150 and result['counts'] == EXPECTED_COUNTS
    return {'clients':len(result['registry']), 'counts':result['counts'], 'scope':'synthetic-sandbox-only'}


def main():
    parser = argparse.ArgumentParser(description='Criar 150 clientes sintéticos, 75 por SaaS; sem recuperação real.')
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    try:
        print(encode(populate(Store(args.db,seed_demo=False))))
    except Problem as error:
        parser.exit(1,error.message+'\n')


if __name__ == '__main__':
    main()
