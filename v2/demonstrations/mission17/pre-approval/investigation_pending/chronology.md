# CENTERWAY — execução local observável

**SOMENTE ENSAIO SINTÉTICO. Uma fixture C04 não comprova inferência real; efeitos/resultados sintéticos não comprovam execução externa ou recuperação real.**

Gerado: 2026-10-26T11:20:45.723770+00:00

## Resultado efetivamente calculado

```json
{
  "scenario": "investigation_pending",
  "classification": "synthetic_test_only",
  "case_state": "awaiting_investigation",
  "blockers": [
    "operator_investigation_missing"
  ],
  "ai": [],
  "effects": 0,
  "samples": 0,
  "c06": [],
  "case_closed": false,
  "real_recovery_demonstrated": false,
  "external_execution": "blocked"
}
```

## Cronologia completa

A ordenação usa o momento de registo; occurred_at/períodos das declarações permanecem nos outputs, sem transformar uma fixture histórica numa observação real.

### 1. 2026-10-26T11:03:47.118810+00:00 — M06

Participação: supplied_synthetic_contract

```json
{
  "tenant": "collaboration",
  "version": 1,
  "parent_hash": null,
  "content_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.118810+00:00",
  "record_hash": "c3a86dc4bcb76947b6b472e1fcc6194cff701416736cc787927e4daa56cd0502",
  "config": {
    "capabilities": [
      {
        "conditions": [
          {
            "evidence_ref": "operation-state",
            "field": "paused",
            "operator": "eq",
            "value": true
          }
        ],
        "description": "Fictional declared capability for proposal tests only; no executor or real authorization.",
        "id": "reopen-delivery-queue",
        "permissions": {
          "required_role": "operator",
          "requires_human_approval": true
        },
        "verification": {
          "operational": [
            {
              "evidence_ref": "operation-state",
              "field": "paused",
              "operator": "eq",
              "value": false
            }
          ],
          "value": [
            {
              "evidence_ref": "value-snapshot",
              "field": "outcome_count",
              "operator": "gte",
              "value": 3
            }
          ],
          "value_goal_refs": [
            "deliver-agreed-work"
          ]
        }
      }
    ],
    "customers": {
      "description": "Fictional account identity contract only; no customer records.",
      "entity": "account",
      "id_field": "account_id"
    },
    "data_classification": "synthetic",
    "events": [
      {
        "customer_id_field": "account_id",
        "description": "Synthetic declared outcome event schema, not a received event.",
        "fields": [
          {
            "name": "account_id",
            "required": true,
            "type": "string"
          },
          {
            "name": "occurred_at",
            "required": true,
            "type": "timestamp"
          }
        ],
        "id": "item-completed",
        "source_ref": "fixture:collaboration:event-definition"
      }
    ],
    "evidence": [
      {
        "availability": "declared",
        "description": "Synthetic declared operation state; not a live state read.",
        "event_refs": [],
        "fields": [
          {
            "name": "paused",
            "required": true,
            "type": "boolean"
          }
        ],
        "id": "operation-state",
        "kind": "state",
        "metric_refs": [],
        "source_ref": "fixture:collaboration:state-definition"
      },
      {
        "availability": "declared",
        "description": "Synthetic declared measured outcome for a supplier-defined evaluation period. No data is collected.",
        "event_refs": [],
        "fields": [
          {
            "name": "outcome_count",
            "required": true,
            "type": "integer"
          }
        ],
        "id": "value-snapshot",
        "kind": "metric",
        "metric_refs": [
          "completed-items"
        ],
        "source_ref": "fixture:collaboration:value-definition"
      },
      {
        "availability": "declared",
        "description": "Fictional owner-declared corroborating snapshot, not a connector read.",
        "event_refs": [],
        "fields": [
          {
            "name": "delay_seconds",
            "required": true,
            "type": "number"
          }
        ],
        "id": "processing-snapshot",
        "kind": "metric",
        "metric_refs": [
          "processing-delay"
        ],
        "source_ref": "fixture:collaboration:processing-evidence"
      }
    ],
    "metrics": [
      {
        "description": "Synthetic owner-supplied outcome count; no automatic computation is implemented.",
        "event_refs": [
          "item-completed"
        ],
        "id": "completed-items",
        "source_ref": "fixture:collaboration:metric-definition",
        "unit": "count",
        "value_type": "integer"
      },
      {
        "description": "Fictional owner-declared processing delay sample. Not a discovered business metric.",
        "event_refs": [],
        "id": "processing-delay",
        "source_ref": "fixture:collaboration:processing-metric",
        "unit": "seconds",
        "value_type": "number"
      }
    ],
    "product": {
      "description": "Synthetic collaborative work product. All declarations below are fictional test inputs, not real customer objectives.",
      "name": "Fictional Collaboration"
    },
    "provenance": {
      "recorded_at": "2026-10-25T00:00:00Z",
      "source_ref": "fixture:collaboration:m08-owner-config",
      "supplied_by": "synthetic-fixture-author"
    },
    "schema_version": 1,
    "tenant": "collaboration",
    "value_goals": [
      {
        "description": "Fictional owner-declared value objective: deliver-agreed-work. No real goal is inferred.",
        "evidence_refs": [
          "value-snapshot",
          "processing-snapshot"
        ],
        "id": "deliver-agreed-work",
        "metric_refs": [
          "completed-items",
          "processing-delay"
        ]
      }
    ]
  }
}
```

### 2. 2026-10-26T11:03:47.125454+00:00 — C02 criteria

Participação: supplied_synthetic_criteria

```json
{
  "tenant": "collaboration",
  "version": 1,
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "parent_hash": null,
  "content_hash": "ca1c874ceb2f0617fe42d0001a9ef99b6463980ba8aa173bd643a4e49de4fbe0",
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.125454+00:00",
  "record_hash": "54fb4c582eac9e8c8a02132b8cf37d67bf56f3cebe2bb584c968da972628e8b5",
  "document": {
    "config_version": 1,
    "criteria": [
      {
        "aggregation": "mean",
        "cadence_seconds": 1,
        "comparison": "gt",
        "coverage": "aligned_complete",
        "description": "Fictional supplier criterion for contract QA only; not a recommended threshold.",
        "dimension": "operational",
        "evidence_refs": [
          "processing-snapshot"
        ],
        "goal_refs": [
          "deliver-agreed-work"
        ],
        "id": "operational-degradation",
        "method": "threshold",
        "metric_ref": "processing-delay",
        "source": {
          "definition_id": "processing-delay",
          "field": "value",
          "kind": "metric"
        },
        "threshold": 10,
        "threshold_unit": "seconds",
        "window_seconds": 2
      },
      {
        "aggregation": "sum",
        "cadence_seconds": 1,
        "comparison": "lt",
        "coverage": "aligned_complete",
        "description": "Fictional supplier criterion for contract QA only; not a recommended threshold.",
        "dimension": "value",
        "evidence_refs": [
          "value-snapshot"
        ],
        "goal_refs": [
          "deliver-agreed-work"
        ],
        "id": "value-loss",
        "method": "absolute_change",
        "metric_ref": "completed-items",
        "source": {
          "definition_id": "value-snapshot",
          "field": "outcome_count",
          "kind": "evidence"
        },
        "threshold": -3,
        "threshold_unit": "count",
        "window_seconds": 2
      }
    ],
    "provenance": {
      "recorded_at": "2026-10-25T00:00:00Z",
      "source_ref": "fixture:collaboration:m08-owner-criteria",
      "supplied_by": "synthetic-fixture-author"
    },
    "schema_version": 1,
    "tenant": "collaboration"
  }
}
```

### 3. 2026-10-26T11:03:47.143940+00:00 — command initialize

Participação: human_supplied_test_profile

```json
{
  "id": 1,
  "operation": "initialize",
  "participation": "human_supplied_test_profile",
  "payload": {
    "input_hashes": {
      "configuration.json": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
      "criteria.json": "ca1c874ceb2f0617fe42d0001a9ef99b6463980ba8aa173bd643a4e49de4fbe0",
      "initial-evidence.json": "e74e741d0aaeaf142c7a7fca1e84356773bf1d810a6fb0339701ccedf5e5c9ce",
      "investigation.json": "8be1e8a3e448c938d769e2ddd052f4cc79417cd161baf7ad625ceb305c77fe67"
    },
    "profile": {
      "as_of": "2026-10-26T11:03:46.000000Z",
      "case_id": "observed-cycle",
      "classification": "synthetic",
      "customer": "fictional-account",
      "fault": "none",
      "operator": "operator",
      "real_recovery_demonstrated": false,
      "scenario": "investigation_pending",
      "tenant": "collaboration",
      "usage_step": 2
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.143940+00:00",
  "previous_hash": null,
  "record_hash": "21d49d43da3e4f745c6ca06e6fd00537ad2dbfcf015be427e20110a0a4444d85"
}
```

### 4. 2026-10-26T11:03:47.190709+00:00 — command login

Participação: human_session

```json
{
  "id": 2,
  "operation": "login",
  "participation": "human_session",
  "payload": {
    "expires_at": "2026-10-26T12:03:47.189359+00:00",
    "user": "operator"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.190709+00:00",
  "previous_hash": "21d49d43da3e4f745c6ca06e6fd00537ad2dbfcf015be427e20110a0a4444d85",
  "record_hash": "dc2ee28c667ac75031e134af62dddff0be81f7ca5e931ae27c6f9e3bb460a935"
}
```

### 5. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 1,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "metric",
  "definition_id": "processing-delay",
  "source_ref": "fixture:collaboration:processing-metric",
  "external_id": "fictional-processing-delay-0",
  "occurred_at": "2026-10-26T11:03:43.000000Z",
  "period_start": "2026-10-26T11:03:42.000000Z",
  "period_end": "2026-10-26T11:03:43.000000Z",
  "payload": {
    "value": 5
  },
  "content_hash": "b150f30c06a177f6b02d06a713b76d5ccd9cb1bdea084a25515fd9b5ba2e797e",
  "fact_hash": "d56964977ad5d003fac1a40e4bbeb8f511fa4b4724ac0dc6b4e93f66f162d68b",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "f42544272167587f9a5791617ae099f070744651652787368bfffccbe845ecd1"
}
```

### 6. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 2,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "processing-snapshot",
  "source_ref": "fixture:collaboration:processing-evidence",
  "external_id": "fictional-processing-snapshot-0",
  "occurred_at": "2026-10-26T11:03:43.000000Z",
  "period_start": "2026-10-26T11:03:42.000000Z",
  "period_end": "2026-10-26T11:03:43.000000Z",
  "payload": {
    "delay_seconds": 5
  },
  "content_hash": "89ec9518cadef755bb0af5739c128ff0789d2a44ef004e998b50fa940e852727",
  "fact_hash": "7bdbe1ee4c39791f432ac591ab63d2edbbbddff7c82c897c5f79ce1764b40e1e",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "5f06f4d4b8751975bc78ff5f3727a0cea7a6197bb2ef2449022e4eadd2f8ce77"
}
```

### 7. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 3,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "value-snapshot",
  "source_ref": "fixture:collaboration:value-definition",
  "external_id": "fictional-value-snapshot-0",
  "occurred_at": "2026-10-26T11:03:43.000000Z",
  "period_start": "2026-10-26T11:03:42.000000Z",
  "period_end": "2026-10-26T11:03:43.000000Z",
  "payload": {
    "outcome_count": 6
  },
  "content_hash": "2e7d9b7436f54b932f3317a6e40ca183ed6c934d50c7a436afe96ba6b8b44fe9",
  "fact_hash": "4f129a3e34c79633b45e8ebb0b0c7a88e36b649bc602308982b8a5a399d698c5",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "ce2bdf43a62ee4540f5e65c2ca6cbeef21e7c710e8ec705301c3932da5beb331"
}
```

### 8. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 4,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "metric",
  "definition_id": "processing-delay",
  "source_ref": "fixture:collaboration:processing-metric",
  "external_id": "fictional-processing-delay-1",
  "occurred_at": "2026-10-26T11:03:44.000000Z",
  "period_start": "2026-10-26T11:03:43.000000Z",
  "period_end": "2026-10-26T11:03:44.000000Z",
  "payload": {
    "value": 5
  },
  "content_hash": "85b7868084cf011a46fe26cf675e954c45dc9a5114058cf902a5dacf57a2de5e",
  "fact_hash": "55297390ae962a4366e08b9b56351499839ea188d53ee63611801ac59a43816d",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "53d91256471fcee4bbfad1491d4467ae6ec9fbd04964bf86e8f1005f9c03e1f0"
}
```

### 9. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 5,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "processing-snapshot",
  "source_ref": "fixture:collaboration:processing-evidence",
  "external_id": "fictional-processing-snapshot-1",
  "occurred_at": "2026-10-26T11:03:44.000000Z",
  "period_start": "2026-10-26T11:03:43.000000Z",
  "period_end": "2026-10-26T11:03:44.000000Z",
  "payload": {
    "delay_seconds": 5
  },
  "content_hash": "2480ed3c67a87c2cbadac4ec56de043acf61f068cecb6ce165cabab38e73c9f1",
  "fact_hash": "bd27ed8f7f5e63619901598650f342dabde3f70d5ec3d20d8a10d7ea4b8ae907",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "93bb886db8827dd15230670a54bfaddc996aea2fc21fc9e6ada5542d082d638f"
}
```

### 10. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 6,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "value-snapshot",
  "source_ref": "fixture:collaboration:value-definition",
  "external_id": "fictional-value-snapshot-1",
  "occurred_at": "2026-10-26T11:03:44.000000Z",
  "period_start": "2026-10-26T11:03:43.000000Z",
  "period_end": "2026-10-26T11:03:44.000000Z",
  "payload": {
    "outcome_count": 6
  },
  "content_hash": "512bdec52a94cd1297a1936e5f63c07bcdd326600414bf71fa5018b3f65cd4ea",
  "fact_hash": "a2103d66169397bfc9bc0e567194cdf45c79259b95f882e124a10121c65d78cf",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "bd7b17ef114a94ad8397e5c4a5bba1b33dfba720a3e1ec907bffe36140489926"
}
```

### 11. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 7,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "metric",
  "definition_id": "processing-delay",
  "source_ref": "fixture:collaboration:processing-metric",
  "external_id": "fictional-processing-delay-2",
  "occurred_at": "2026-10-26T11:03:45.000000Z",
  "period_start": "2026-10-26T11:03:44.000000Z",
  "period_end": "2026-10-26T11:03:45.000000Z",
  "payload": {
    "value": 20
  },
  "content_hash": "c7945abe74de23db329ee0de35c60113265a078447d98f2f77b7b681952ed064",
  "fact_hash": "184baf986cd2996c7298e9240fccfa46be8037764703d83f9841ad19434a303f",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "994339211e397c7e881644d34b2c948ce0ec665fc79a0dab1dd2afb0f3cd322d"
}
```

### 12. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 8,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "processing-snapshot",
  "source_ref": "fixture:collaboration:processing-evidence",
  "external_id": "fictional-processing-snapshot-2",
  "occurred_at": "2026-10-26T11:03:45.000000Z",
  "period_start": "2026-10-26T11:03:44.000000Z",
  "period_end": "2026-10-26T11:03:45.000000Z",
  "payload": {
    "delay_seconds": 20
  },
  "content_hash": "291a737bc7c35e91482ad3ebf4cfb86bef2dbfdbb4fc484ef775222b39e117b4",
  "fact_hash": "d685554c90da46c0e15984e07c4c7c21644c0744e9542add8926cb5e8ba3de1c",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "b6aad0456af0516a516904421db8c181c5d9f4534c8a40cdff3b506de8991a47"
}
```

### 13. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 9,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "value-snapshot",
  "source_ref": "fixture:collaboration:value-definition",
  "external_id": "fictional-value-snapshot-2",
  "occurred_at": "2026-10-26T11:03:45.000000Z",
  "period_start": "2026-10-26T11:03:44.000000Z",
  "period_end": "2026-10-26T11:03:45.000000Z",
  "payload": {
    "outcome_count": 1
  },
  "content_hash": "83e1efacafa40f6af8ba18f4c729a8c64c5163f6479744d03ec90aa33cffd927",
  "fact_hash": "a21b7a2ef560aa1f660ced4f490beadc316c9bfc8a7aceb68a3719a856b83e4d",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "b539f8ac627752c711844b9bc0d18a4f5fdf9717e259b44265821c05faadc493"
}
```

### 14. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 10,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "metric",
  "definition_id": "processing-delay",
  "source_ref": "fixture:collaboration:processing-metric",
  "external_id": "fictional-processing-delay-3",
  "occurred_at": "2026-10-26T11:03:46.000000Z",
  "period_start": "2026-10-26T11:03:45.000000Z",
  "period_end": "2026-10-26T11:03:46.000000Z",
  "payload": {
    "value": 20
  },
  "content_hash": "cdcd5a7aa0a76918db445ede964246e5b00c84fe346cbb28e6fad4fe56fd1726",
  "fact_hash": "8b898c30221ede1e3625eb3c8f56b86e0003aaaa10b0912cb319e94f04729ae9",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "04afc22ace5ba841713a6cfe96955ad6a51c134948cd7203a882b623045ef3a7"
}
```

### 15. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 11,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "processing-snapshot",
  "source_ref": "fixture:collaboration:processing-evidence",
  "external_id": "fictional-processing-snapshot-3",
  "occurred_at": "2026-10-26T11:03:46.000000Z",
  "period_start": "2026-10-26T11:03:45.000000Z",
  "period_end": "2026-10-26T11:03:46.000000Z",
  "payload": {
    "delay_seconds": 20
  },
  "content_hash": "f789843be7cfcc9c8d48c7848f01b660385c360b3dbec7070671942cea8b8344",
  "fact_hash": "478598734f967b58db0c3ea0f50b05c73a2a21a5733bd4ecfaa5ee5b4912acc8",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "246a73b8129d6616670e25cc4300457575aa2c5956b37053b50e53ea03b6bad7"
}
```

### 16. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 12,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "value-snapshot",
  "source_ref": "fixture:collaboration:value-definition",
  "external_id": "fictional-value-snapshot-3",
  "occurred_at": "2026-10-26T11:03:46.000000Z",
  "period_start": "2026-10-26T11:03:45.000000Z",
  "period_end": "2026-10-26T11:03:46.000000Z",
  "payload": {
    "outcome_count": 1
  },
  "content_hash": "4bc61e32629fabde1c384295b894b2fa0cd5bd322c3cd4daaf6a8141b2f05ee8",
  "fact_hash": "d652cb1a54f15cf1ba7aded7559eb1276067a3985d7c431f03d13e7cd2e6c212",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "abd440e762a4f2a61d4342dba1b623f8221ff80aedf5e486dcbd164bdc941849"
}
```

### 17. 2026-10-26T11:03:47.193936Z — M07

Participação: synthetic_source_claim

```json
{
  "id": 13,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "config_version": 1,
  "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "kind": "evidence",
  "definition_id": "operation-state",
  "source_ref": "fixture:collaboration:state-definition",
  "external_id": "fictional-paused-observation",
  "occurred_at": "2026-10-26T11:03:46.000000Z",
  "period_start": null,
  "period_end": null,
  "payload": {
    "paused": true
  },
  "content_hash": "1379a1b2a06ff4e2f8f87d323dc6a0584fdd110a4e204e4dd851df48dd012bf9",
  "fact_hash": "1f34fb475d955bdc1df9576956de6cc885a54ad9471f8b83269729bc741333ee",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:47.193936Z",
  "record_hash": "061fc6a725f2de820d56bba66a5e4a044f6143ecab170e2c62238bba99eb5a4f"
}
```

### 18. 2026-10-26T11:03:47.196684+00:00 — command M07_ingest

Participação: human_supplied_synthetic_evidence

```json
{
  "id": 3,
  "operation": "M07_ingest",
  "participation": "human_supplied_synthetic_evidence",
  "payload": {
    "input_hash": "e74e741d0aaeaf142c7a7fca1e84356773bf1d810a6fb0339701ccedf5e5c9ce",
    "result": {
      "batch_id": 1,
      "classification": "synthetic",
      "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
      "config_version": 1,
      "customer": "fictional-account",
      "duplicates": 0,
      "inserted": 13,
      "operational_state": "inactive",
      "record_ids": [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13
      ],
      "reused": false,
      "tenant": "collaboration"
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.196684+00:00",
  "previous_hash": "dc2ee28c667ac75031e134af62dddff0be81f7ca5e931ae27c6f9e3bb460a935",
  "record_hash": "bc2a5b0726f4a3ac99ab930b04428ceefb50fb8e72f691cab0702631d3f27f04"
}
```

### 19. 2026-10-26T11:03:47.199732+00:00 — M14 opening

Participação: explicit_local_case_registration

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "request_id": "observed-cycle",
  "payload": {
    "cycle_number": 1,
    "legacy_upgrade": false,
    "new_evidence_ids": [],
    "predecessor_closure_hash": null,
    "previous_case_id": null,
    "reason": "initial_registration",
    "session_hash": null
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.199732+00:00",
  "record_hash": "444a8041211f88d1c57af95e9f50a5ae93f8549fb574be003f43a3b4fcf7b0dd"
}
```

### 20. 2026-10-26T11:03:47.203838+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 1,
  "parent_hash": null,
  "payload": {
    "basis": {},
    "blockers": [
      "not_processed"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {},
    "state": "awaiting_data"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.203838+00:00",
  "record_hash": "d8aea814814afbafb19c9312b85eaf7ef62faca7a3e2dbcda36d4f7f9546406b"
}
```

### 21. 2026-10-26T11:03:47.218412+00:00 — C02

Participação: automatic_deterministic_assessment

```json
{
  "id": 1,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "criteria_version": 1,
  "request_hash": "706375c318cb013dd79ee0a61cc3684fe62b381cd3bb20f519d0fa5f14c49d42",
  "payload": {
    "algorithm": "c02-adaptive-v1",
    "as_of": "2026-10-26T11:03:46.000000Z",
    "classification": "synthetic",
    "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
    "config_version": 1,
    "criteria_hash": "ca1c874ceb2f0617fe42d0001a9ef99b6463980ba8aa173bd643a4e49de4fbe0",
    "criteria_results": [
      {
        "contradictions": [],
        "criterion_id": "operational-degradation",
        "dimension": "operational",
        "issues": [],
        "measured": {
          "denominator": "1",
          "numerator": "20"
        },
        "state": "demonstrated",
        "windows": {
          "current": {
            "aggregate": {
              "denominator": "1",
              "numerator": "20"
            },
            "contradictions": [],
            "end": "2026-10-26T11:03:46.000000Z",
            "evidence_ids": [
              7,
              8,
              10,
              11
            ],
            "issues": [],
            "start": "2026-10-26T11:03:44.000000Z"
          }
        }
      },
      {
        "contradictions": [],
        "criterion_id": "value-loss",
        "dimension": "value",
        "issues": [],
        "measured": {
          "denominator": "1",
          "numerator": "-10"
        },
        "state": "demonstrated",
        "windows": {
          "baseline": {
            "aggregate": {
              "denominator": "1",
              "numerator": "12"
            },
            "contradictions": [],
            "end": "2026-10-26T11:03:44.000000Z",
            "evidence_ids": [
              3,
              6
            ],
            "issues": [],
            "start": "2026-10-26T11:03:42.000000Z"
          },
          "current": {
            "aggregate": {
              "denominator": "1",
              "numerator": "2"
            },
            "contradictions": [],
            "end": "2026-10-26T11:03:46.000000Z",
            "evidence_ids": [
              9,
              12
            ],
            "issues": [],
            "start": "2026-10-26T11:03:44.000000Z"
          }
        }
      }
    ],
    "criteria_snapshot": {
      "config_version": 1,
      "criteria": [
        {
          "aggregation": "mean",
          "cadence_seconds": 1,
          "comparison": "gt",
          "coverage": "aligned_complete",
          "description": "Fictional supplier criterion for contract QA only; not a recommended threshold.",
          "dimension": "operational",
          "evidence_refs": [
            "processing-snapshot"
          ],
          "goal_refs": [
            "deliver-agreed-work"
          ],
          "id": "operational-degradation",
          "method": "threshold",
          "metric_ref": "processing-delay",
          "source": {
            "definition_id": "processing-delay",
            "field": "value",
            "kind": "metric"
          },
          "threshold": 10,
          "threshold_unit": "seconds",
          "window_seconds": 2
        },
        {
          "aggregation": "sum",
          "cadence_seconds": 1,
          "comparison": "lt",
          "coverage": "aligned_complete",
          "description": "Fictional supplier criterion for contract QA only; not a recommended threshold.",
          "dimension": "value",
          "evidence_refs": [
            "value-snapshot"
          ],
          "goal_refs": [
            "deliver-agreed-work"
          ],
          "id": "value-loss",
          "method": "absolute_change",
          "metric_ref": "completed-items",
          "source": {
            "definition_id": "value-snapshot",
            "field": "outcome_count",
            "kind": "evidence"
          },
          "threshold": -3,
          "threshold_unit": "count",
          "window_seconds": 2
        }
      ],
      "provenance": {
        "recorded_at": "2026-10-25T00:00:00Z",
        "source_ref": "fixture:collaboration:m08-owner-criteria",
        "supplied_by": "synthetic-fixture-author"
      },
      "schema_version": 1,
      "tenant": "collaboration"
    },
    "criteria_version": 1,
    "customer": "fictional-account",
    "evidence": [
      {
        "id": 1,
        "record_hash": "f42544272167587f9a5791617ae099f070744651652787368bfffccbe845ecd1"
      },
      {
        "id": 2,
        "record_hash": "5f06f4d4b8751975bc78ff5f3727a0cea7a6197bb2ef2449022e4eadd2f8ce77"
      },
      {
        "id": 3,
        "record_hash": "ce2bdf43a62ee4540f5e65c2ca6cbeef21e7c710e8ec705301c3932da5beb331"
      },
      {
        "id": 4,
        "record_hash": "53d91256471fcee4bbfad1491d4467ae6ec9fbd04964bf86e8f1005f9c03e1f0"
      },
      {
        "id": 5,
        "record_hash": "93bb886db8827dd15230670a54bfaddc996aea2fc21fc9e6ada5542d082d638f"
      },
      {
        "id": 6,
        "record_hash": "bd7b17ef114a94ad8397e5c4a5bba1b33dfba720a3e1ec907bffe36140489926"
      },
      {
        "id": 7,
        "record_hash": "994339211e397c7e881644d34b2c948ce0ec665fc79a0dab1dd2afb0f3cd322d"
      },
      {
        "id": 8,
        "record_hash": "b6aad0456af0516a516904421db8c181c5d9f4534c8a40cdff3b506de8991a47"
      },
      {
        "id": 9,
        "record_hash": "b539f8ac627752c711844b9bc0d18a4f5fdf9717e259b44265821c05faadc493"
      },
      {
        "id": 10,
        "record_hash": "04afc22ace5ba841713a6cfe96955ad6a51c134948cd7203a882b623045ef3a7"
      },
      {
        "id": 11,
        "record_hash": "246a73b8129d6616670e25cc4300457575aa2c5956b37053b50e53ea03b6bad7"
      },
      {
        "id": 12,
        "record_hash": "abd440e762a4f2a61d4342dba1b623f8221ff80aedf5e486dcbd164bdc941849"
      },
      {
        "id": 13,
        "record_hash": "061fc6a725f2de820d56bba66a5e4a044f6143ecab170e2c62238bba99eb5a4f"
      }
    ],
    "operational_deterioration": {
      "criterion_ids": [
        "operational-degradation"
      ],
      "state": "demonstrated"
    },
    "operational_state": "inactive",
    "proof_scope": "declared_criteria_and_supplied_evidence",
    "tenant": "collaboration",
    "through": 13,
    "value_loss": {
      "criterion_ids": [
        "value-loss"
      ],
      "state": "demonstrated"
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.218412+00:00",
  "record_hash": "640bd7c14c20e4322d90aa916aeb89109d98768ec7c51e677165227efdece811",
  "reused": true
}
```

### 22. 2026-10-26T11:03:47.220749+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 2,
  "parent_hash": "d8aea814814afbafb19c9312b85eaf7ef62faca7a3e2dbcda36d4f7f9546406b",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:03:46.000000Z",
      "source_hash": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
      "source_heads": {
        "config_version": 1,
        "criteria_version": 1,
        "eligible_ids": [
          1,
          2,
          3,
          4,
          5,
          6,
          7,
          8,
          9,
          10,
          11,
          12,
          13
        ],
        "through": 13
      }
    },
    "blockers": [
      "c02_recorded"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
        "id": 1,
        "record_hash": "640bd7c14c20e4322d90aa916aeb89109d98768ec7c51e677165227efdece811"
      }
    },
    "state": "awaiting_investigation"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.220749+00:00",
  "record_hash": "78902fd0866712bafd6a328b4fececf4e9a26751ac2b067e6a325eaed711fd8e"
}
```

### 23. 2026-10-26T11:03:47.236922+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 3,
  "parent_hash": "78902fd0866712bafd6a328b4fececf4e9a26751ac2b067e6a325eaed711fd8e",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:03:46.000000Z",
      "source_hash": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
      "source_heads": {
        "config_version": 1,
        "criteria_version": 1,
        "eligible_ids": [
          1,
          2,
          3,
          4,
          5,
          6,
          7,
          8,
          9,
          10,
          11,
          12,
          13
        ],
        "through": 13
      }
    },
    "blockers": [
      "operator_investigation_missing"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
        "id": 1,
        "record_hash": "640bd7c14c20e4322d90aa916aeb89109d98768ec7c51e677165227efdece811"
      }
    },
    "state": "awaiting_investigation"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.236922+00:00",
  "record_hash": "ec043f4f3bc1288bc400984c138c3f40415d85b0ad24851e59d5c4b9bab55d44"
}
```

### 24. 2026-10-26T11:03:47.240342+00:00 — command orchestrator_advance

Participação: automatic_bounded_processing

```json
{
  "id": 4,
  "operation": "orchestrator_advance",
  "participation": "automatic_bounded_processing",
  "payload": {
    "ai_kind": "unavailable",
    "checkpoint": {
      "actor": "operator",
      "case_id": "observed-cycle",
      "created_at": "2026-10-26T11:03:47.236922+00:00",
      "customer": "fictional-account",
      "parent_hash": "78902fd0866712bafd6a328b4fececf4e9a26751ac2b067e6a325eaed711fd8e",
      "payload": {
        "basis": {
          "as_of": "2026-10-26T11:03:46.000000Z",
          "source_hash": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
          "source_heads": {
            "config_version": 1,
            "criteria_version": 1,
            "eligible_ids": [
              1,
              2,
              3,
              4,
              5,
              6,
              7,
              8,
              9,
              10,
              11,
              12,
              13
            ],
            "through": 13
          }
        },
        "blockers": [
          "operator_investigation_missing"
        ],
        "core_transition_authorized": false,
        "operational_state": "inactive",
        "real_recovery_demonstrated": false,
        "refs": {
          "c02": {
            "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
            "id": 1,
            "record_hash": "640bd7c14c20e4322d90aa916aeb89109d98768ec7c51e677165227efdece811"
          }
        },
        "state": "awaiting_investigation"
      },
      "record_hash": "ec043f4f3bc1288bc400984c138c3f40415d85b0ad24851e59d5c4b9bab55d44",
      "tenant": "collaboration",
      "version": 3
    },
    "external_execution": "blocked"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:47.240342+00:00",
  "previous_hash": "bc2a5b0726f4a3ac99ab930b04428ceefb50fb8e72f691cab0702631d3f27f04",
  "record_hash": "497f0a11e3edb8dbc2f3143dd32a9c809ac9e0c9c9168e36e1f9c3df8300c7ba"
}
```

## Limitações

- No autonomous investigation: C03 requires an operator-supplied document.
- No external research or SaaS connector.
- No real AI verified by a supplied test fixture; no configured AI means unavailable.
- Only synthetic persisted effects, never real customer/value recovery.
- No automatic resolution, retry or erasure of uncertain executions.
- Human approval is an explicit local session assertion, not biometric verification.
- C06 does not close the case; M14 remains explicit.
- CLI only; pilot/production/HTTP unchanged. Local row hashes are not external audit signatures.
