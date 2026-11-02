"""CENTERWAY TestLab: deterministic offline synthetic producer; NO API or network writes."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import time
import uuid

NAMESPACE = uuid.UUID("4f55c1ef-f304-485f-8c80-b7c99e39ed71")
COMPANY = "SYNTHETIC FlowPilot SaaS"
GROUPS = ("excellent", "good", "median", "deteriorating", "inconclusive")
NAMES = (
    "Alfa Consultoria", "Beta Logística", "Clara Serviços", "Delta Escritórios",
    "Eco Gestão", "Faro Digital", "Gama Comércio", "Horizonte RH",
    "Íris Projetos", "Jade Contabilidade", "Kappa Equipa", "Lume Operações",
    "Mova Comércio", "Norte Atendimento", "Órbita Serviços", "Ponto Apoio",
    "Quinta Operações", "Rumo Gestão", "Soma Consultoria", "Trilho Digital",
)

def clients():
    return [{
        "client_id": str(uuid.uuid5(NAMESPACE, f"client-{i:02d}")),
        "name": f"SYNTHETIC {NAMES[i]}",
        "group": GROUPS[i // 4],
        "objective": "Reduce minutes per administrative task",
        "unit": "min", "direction": "lower", "baseline": 100.0,
        "minimum_acceptable": 75.0, "target": 60.0, "synthetic_only": True,
    } for i in range(20)]

def value_for(i, cycle):
    group, variant = divmod(i, 4)
    jitter = ((cycle * 3 + i * 7) % 5) - 2
    if group == 0: return float(46 + variant * 2 + jitter), "verified", "above_target"
    if group == 1: return float(61 + variant * 3 + jitter), "verified", "healthy"
    if group == 2: return float(75 + variant * 5 + jitter), "partial" if variant == 3 else "verified", "borderline"
    if group == 3:
        # One later improvement. Do NOT infer a causal link to an intervention.
        v = 70 + cycle * 4 + variant * 2 if variant < 2 else (
            91 + jitter if variant == 2 else 99 - 7 * max(0, cycle - 5))
        return float(max(45, min(v, 120))), "verified", "deterioration_or_recovery"
    if variant == 0: return None, "partial", "missing_measurement"
    if variant == 1: return float(63 + jitter), "disputed", "contradictory_source"
    if variant == 2: return (None if cycle % 2 else float(82 + jitter)), "partial", "incomplete_period"
    return float(57 + jitter), "partial", "usage_not_business_outcome"

def measurements(cycle, origin, interval=120):
    if cycle < 0 or interval < 2: raise ValueError("invalid cycle or interval")
    result = []
    for i, client in enumerate(clients()):
        value, quality, oracle = value_for(i, cycle)
        start = origin + dt.timedelta(seconds=cycle * interval)
        end = start + dt.timedelta(seconds=interval)
        result.append({
            "event_id": str(uuid.uuid5(NAMESPACE, f"{i}-{cycle}")),
            "client_id": client["client_id"], "synthetic_only": True,
            "period_start": start.isoformat().replace("+00:00", "Z"),
            "period_end": end.isoformat().replace("+00:00", "Z"),
            "evidence_type": "usage" if i == 19 else "outcome",
            "quality": quality, "observed_value": value, "unit": "min",
            "reference": f"synthetic://centerway/testlab/{i+1:02d}/{cycle}",
            "expected_case_for_test_oracle_only": oracle,
        })
    return result

def main():
    p = argparse.ArgumentParser(description="Offline TestLab: no external services used")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=int, default=120)
    p.add_argument("--catalog", action="store_true")
    p.add_argument("--realtime", action="store_true")
    args = p.parse_args()
    if not 1 <= args.cycles <= 500: p.error("cycles must be 1..500")
    if not 2 <= args.interval <= 3600: p.error("interval must be 2..3600")
    if args.catalog:
        print(json.dumps({"company": COMPANY, "clients": clients()}, ensure_ascii=False))
        return
    # First emitted period is already closed; following periods close as time advances.
    origin = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(seconds=args.interval)
    for cycle in range(args.cycles):
        print(json.dumps({"cycle": cycle, "company": COMPANY,
            "measurements": measurements(cycle, origin, args.interval)}, ensure_ascii=False), flush=True)
        if args.realtime and cycle < args.cycles - 1: time.sleep(args.interval)

if __name__ == "__main__":
    main()
