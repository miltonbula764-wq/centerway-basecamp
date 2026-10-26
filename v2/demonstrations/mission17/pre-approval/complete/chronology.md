# CENTERWAY — execução local observável

**SOMENTE ENSAIO SINTÉTICO. Uma fixture C04 não comprova inferência real; efeitos/resultados sintéticos não comprovam execução externa ou recuperação real.**

Gerado: 2026-10-26T11:20:45.609195+00:00

## Resultado efetivamente calculado

```json
{
  "scenario": "complete",
  "classification": "synthetic_test_only",
  "case_state": "awaiting_approval",
  "blockers": [
    "explicit_human_approval_required"
  ],
  "ai": [
    {
      "inference_kind": "test_fixture",
      "reported_model": "explicit-fixture-not-ai",
      "failure": null
    }
  ],
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

### 1. 2026-10-26T11:01:31.342489+00:00 — M06

Participação: supplied_synthetic_contract

```json
{
  "tenant": "collaboration",
  "version": 1,
  "parent_hash": null,
  "content_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.342489+00:00",
  "record_hash": "b744f9bb946b8519139505d868da0cce47158488b065386b478e644fa324adae",
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

### 2. 2026-10-26T11:01:31.354942+00:00 — C02 criteria

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
  "created_at": "2026-10-26T11:01:31.354942+00:00",
  "record_hash": "086877d3feed99f6eb72471ce8a3cb92874a27203be13c5c9e140f2c9f769db9",
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

### 3. 2026-10-26T11:01:31.375909+00:00 — command initialize

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
      "initial-evidence.json": "884ebac1f73be1ca39c1be9a7c128289b669f0c4495bd89e3904cae791d11b85",
      "investigation.json": "8be1e8a3e448c938d769e2ddd052f4cc79417cd161baf7ad625ceb305c77fe67"
    },
    "profile": {
      "as_of": "2026-10-26T11:01:30.000000Z",
      "case_id": "observed-cycle",
      "classification": "synthetic",
      "customer": "fictional-account",
      "fault": "none",
      "operator": "operator",
      "real_recovery_demonstrated": false,
      "scenario": "complete",
      "tenant": "collaboration",
      "usage_step": 2
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.375909+00:00",
  "previous_hash": null,
  "record_hash": "f2d789d8bc5a6775c045c287445e925531d0ca874807cbdcf2d45bc244a21d8d"
}
```

### 4. 2026-10-26T11:01:31.459604+00:00 — command login

Participação: human_session

```json
{
  "id": 2,
  "operation": "login",
  "participation": "human_session",
  "payload": {
    "expires_at": "2026-10-26T12:01:31.458159+00:00",
    "user": "operator"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.459604+00:00",
  "previous_hash": "f2d789d8bc5a6775c045c287445e925531d0ca874807cbdcf2d45bc244a21d8d",
  "record_hash": "a579acf58e7f7d212ffca97c9a314dc5b607a928141ea9bb524815eb942598a8"
}
```

### 5. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:27.000000Z",
  "period_start": "2026-10-26T11:01:26.000000Z",
  "period_end": "2026-10-26T11:01:27.000000Z",
  "payload": {
    "value": 5
  },
  "content_hash": "4315456fe0cf3dd331e4c6f96f01a10f8156dd9a8f3ae8016fc2ade6f8674007",
  "fact_hash": "095655a0e263f6a6926978d4b4e668cdf11016c6e3b961146d5260383d2c3eae",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "3383ccc7fda9b896d495604320e747df7298e19dd47bf7957cf27779cf92aa89"
}
```

### 6. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:27.000000Z",
  "period_start": "2026-10-26T11:01:26.000000Z",
  "period_end": "2026-10-26T11:01:27.000000Z",
  "payload": {
    "delay_seconds": 5
  },
  "content_hash": "1fc7700ac0c4f8d5259bd00cbfb8492ff0ef84bb0877886095ceaeca3895199b",
  "fact_hash": "f4c6231440281772438731e913a61701a71263f8ae498cc99104f5b09fe7caa1",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "7173b7ae1e2498cb27fe935c0405f7a476aabd7a0107471eeeb40f97e4ffa6aa"
}
```

### 7. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:27.000000Z",
  "period_start": "2026-10-26T11:01:26.000000Z",
  "period_end": "2026-10-26T11:01:27.000000Z",
  "payload": {
    "outcome_count": 6
  },
  "content_hash": "50cbf4e7b8ad72eb4a4bfe13b363b388f86fc1d2bb1bcc0036726e6b4bbb75e9",
  "fact_hash": "1a1bbba056d7e39a871d7b5bd208b26131921a801b1ced9cbe7c09b7403982dc",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "4a41021179cd2b8bb31e38f72ed0628440000274cae7ee98f440d74b166fc5e5"
}
```

### 8. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:28.000000Z",
  "period_start": "2026-10-26T11:01:27.000000Z",
  "period_end": "2026-10-26T11:01:28.000000Z",
  "payload": {
    "value": 5
  },
  "content_hash": "4193c735419a20f6d09485f71aa8ed007087b18302ea53f1c248628d4dc7c46d",
  "fact_hash": "619bd74cffb3b36c36decea949ece3e28cffe8eeb8b1bb07070ffe7902b86329",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "9f7a99eba074ca8ba095cc89b8b6593f4a797770401a11a4ef0edaba318dc7ff"
}
```

### 9. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:28.000000Z",
  "period_start": "2026-10-26T11:01:27.000000Z",
  "period_end": "2026-10-26T11:01:28.000000Z",
  "payload": {
    "delay_seconds": 5
  },
  "content_hash": "42df480cb63e1c723eec93c81ac21000057532a2265fd2daf14f91cfe0eec3c9",
  "fact_hash": "39ad56de1d024e4691113bb47ccf6be2571c2761ff43c080fbd87412c8d83c65",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "9729bb69ad14d41224a2ac68e1658c99266414e4a1d789be4b87c22f83953985"
}
```

### 10. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:28.000000Z",
  "period_start": "2026-10-26T11:01:27.000000Z",
  "period_end": "2026-10-26T11:01:28.000000Z",
  "payload": {
    "outcome_count": 6
  },
  "content_hash": "73642c0f32b6ff4dbc5591fe24a964ddba895f5b7fa0f0b8add986cb805b92be",
  "fact_hash": "44523c650f644132fb5c5dcdb3079e1af63377228b66c3dce78f1ba0d84bafd2",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "cc593bc447aa9f85d890f43185088269974a2908df69169fe624cc85940654d8"
}
```

### 11. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:29.000000Z",
  "period_start": "2026-10-26T11:01:28.000000Z",
  "period_end": "2026-10-26T11:01:29.000000Z",
  "payload": {
    "value": 20
  },
  "content_hash": "f0cf61169accb386e9b279aaefa150e4571813eebcdf6b0b524e122532a2b204",
  "fact_hash": "8e4d84595f62c390c9fd6c25beebf471c2042b61a9d169b8ed9f48db0cb671bc",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "24dfe732cb5b72356cb562377d2b094aef568d3eb0c23b0c4832e65377292a5d"
}
```

### 12. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:29.000000Z",
  "period_start": "2026-10-26T11:01:28.000000Z",
  "period_end": "2026-10-26T11:01:29.000000Z",
  "payload": {
    "delay_seconds": 20
  },
  "content_hash": "3b50749dc7fceb3a56d0487dc9bf53abb6bfaf3400c9acfa4e6d7d3966718fff",
  "fact_hash": "497ac3f9a9dff25f85a1840006962e16439bfc667b99b53d68c885f105ff4c42",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "db7c10a8b15890afa41f1b8ca2a9407108fda66a861fd61d6df869a5ef593051"
}
```

### 13. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:29.000000Z",
  "period_start": "2026-10-26T11:01:28.000000Z",
  "period_end": "2026-10-26T11:01:29.000000Z",
  "payload": {
    "outcome_count": 1
  },
  "content_hash": "7ebc349e01f050233abd34954138c47172a80ed3ccd01be7bb805ac0ddb2352d",
  "fact_hash": "e8de1ac5ae584b281e1606c3182b8dc8c876f9be672e58debefa9940f1db5332",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "ee1cc5b7484c4ebe81a2f9f1a7cead3c695e89706b5c08bab4c4fa3f8dac4a33"
}
```

### 14. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:30.000000Z",
  "period_start": "2026-10-26T11:01:29.000000Z",
  "period_end": "2026-10-26T11:01:30.000000Z",
  "payload": {
    "value": 20
  },
  "content_hash": "901412552841fe389b3ff3c3624de38346b1b6b754370aea322d21ea23f24af4",
  "fact_hash": "df04e4908c32a17aaba7c72399916663cd9c96cd0703acb03b906bcf70543383",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "2ad207996e772dbb68561bd671f59173e4116ffda6b14efbbe9ae99106dde99c"
}
```

### 15. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:30.000000Z",
  "period_start": "2026-10-26T11:01:29.000000Z",
  "period_end": "2026-10-26T11:01:30.000000Z",
  "payload": {
    "delay_seconds": 20
  },
  "content_hash": "c1bcda8d49f10c6116a98ae8062a21345014a1fca5dd92e11309afc32bb1f139",
  "fact_hash": "e09e04b719b643907f2420cc21f61ff8760b5fd36ce4bc3589ea02062fe10b42",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "8f2bf96a3ff6f533de9ed325f1e9b01c7ec12005f248b5345bd701fa515d576f"
}
```

### 16. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:30.000000Z",
  "period_start": "2026-10-26T11:01:29.000000Z",
  "period_end": "2026-10-26T11:01:30.000000Z",
  "payload": {
    "outcome_count": 1
  },
  "content_hash": "4eb0c56ccf45c294032bc1edb006e4d25c879f3ca5af94af5364bd851d8d6edd",
  "fact_hash": "d18fe79a82fd23491a9306525397bb6d06f977536b4888a7f34f8a721e3fbf99",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "3d9a580156de966eddef2f8511973105e04e2363d62b7ae48094c1ee16c81134"
}
```

### 17. 2026-10-26T11:01:31.463080Z — M07

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
  "occurred_at": "2026-10-26T11:01:30.000000Z",
  "period_start": null,
  "period_end": null,
  "payload": {
    "paused": true
  },
  "content_hash": "6198467cb938c56667fe1f31c961551c0e0f8c6a4a7e5173853c42cf0b75d566",
  "fact_hash": "48894d4496998b4fa3445b6abd02990fa7eaf839358634b37976653d23a2389e",
  "actor": "operator",
  "received_at": "2026-10-26T11:01:31.463080Z",
  "record_hash": "521562f03afb4f2148d4843a8a1aa985880578a2d2f197c54d267f1f9046aab0"
}
```

### 18. 2026-10-26T11:01:31.466185+00:00 — command M07_ingest

Participação: human_supplied_synthetic_evidence

```json
{
  "id": 3,
  "operation": "M07_ingest",
  "participation": "human_supplied_synthetic_evidence",
  "payload": {
    "input_hash": "884ebac1f73be1ca39c1be9a7c128289b669f0c4495bd89e3904cae791d11b85",
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
  "created_at": "2026-10-26T11:01:31.466185+00:00",
  "previous_hash": "a579acf58e7f7d212ffca97c9a314dc5b607a928141ea9bb524815eb942598a8",
  "record_hash": "6c0d1b56930c3ed8faefe5aa2cb477a09ec133637997de4ede229fbfeeae7a5f"
}
```

### 19. 2026-10-26T11:01:31.469679+00:00 — M14 opening

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
  "created_at": "2026-10-26T11:01:31.469679+00:00",
  "record_hash": "63f2c142d5b0ba1526f534e8981d948ee540fdaa4664eac688ad9d4b6cfc20f0"
}
```

### 20. 2026-10-26T11:01:31.474037+00:00 — orchestrator checkpoint

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
  "created_at": "2026-10-26T11:01:31.474037+00:00",
  "record_hash": "296e2de0b351a7aef37ac013949bd154a6bd3aac7c606264211743c0e7392779"
}
```

### 21. 2026-10-26T11:01:31.489446+00:00 — C02

Participação: automatic_deterministic_assessment

```json
{
  "id": 1,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "criteria_version": 1,
  "request_hash": "bba58a76bd6e514fbf58348ccd002556a3e1f77a4f939eede1f76dd7b5c239b8",
  "payload": {
    "algorithm": "c02-adaptive-v1",
    "as_of": "2026-10-26T11:01:30.000000Z",
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
            "end": "2026-10-26T11:01:30.000000Z",
            "evidence_ids": [
              7,
              8,
              10,
              11
            ],
            "issues": [],
            "start": "2026-10-26T11:01:28.000000Z"
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
            "end": "2026-10-26T11:01:28.000000Z",
            "evidence_ids": [
              3,
              6
            ],
            "issues": [],
            "start": "2026-10-26T11:01:26.000000Z"
          },
          "current": {
            "aggregate": {
              "denominator": "1",
              "numerator": "2"
            },
            "contradictions": [],
            "end": "2026-10-26T11:01:30.000000Z",
            "evidence_ids": [
              9,
              12
            ],
            "issues": [],
            "start": "2026-10-26T11:01:28.000000Z"
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
        "record_hash": "3383ccc7fda9b896d495604320e747df7298e19dd47bf7957cf27779cf92aa89"
      },
      {
        "id": 2,
        "record_hash": "7173b7ae1e2498cb27fe935c0405f7a476aabd7a0107471eeeb40f97e4ffa6aa"
      },
      {
        "id": 3,
        "record_hash": "4a41021179cd2b8bb31e38f72ed0628440000274cae7ee98f440d74b166fc5e5"
      },
      {
        "id": 4,
        "record_hash": "9f7a99eba074ca8ba095cc89b8b6593f4a797770401a11a4ef0edaba318dc7ff"
      },
      {
        "id": 5,
        "record_hash": "9729bb69ad14d41224a2ac68e1658c99266414e4a1d789be4b87c22f83953985"
      },
      {
        "id": 6,
        "record_hash": "cc593bc447aa9f85d890f43185088269974a2908df69169fe624cc85940654d8"
      },
      {
        "id": 7,
        "record_hash": "24dfe732cb5b72356cb562377d2b094aef568d3eb0c23b0c4832e65377292a5d"
      },
      {
        "id": 8,
        "record_hash": "db7c10a8b15890afa41f1b8ca2a9407108fda66a861fd61d6df869a5ef593051"
      },
      {
        "id": 9,
        "record_hash": "ee1cc5b7484c4ebe81a2f9f1a7cead3c695e89706b5c08bab4c4fa3f8dac4a33"
      },
      {
        "id": 10,
        "record_hash": "2ad207996e772dbb68561bd671f59173e4116ffda6b14efbbe9ae99106dde99c"
      },
      {
        "id": 11,
        "record_hash": "8f2bf96a3ff6f533de9ed325f1e9b01c7ec12005f248b5345bd701fa515d576f"
      },
      {
        "id": 12,
        "record_hash": "3d9a580156de966eddef2f8511973105e04e2363d62b7ae48094c1ee16c81134"
      },
      {
        "id": 13,
        "record_hash": "521562f03afb4f2148d4843a8a1aa985880578a2d2f197c54d267f1f9046aab0"
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
  "created_at": "2026-10-26T11:01:31.489446+00:00",
  "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1",
  "reused": true
}
```

### 22. 2026-10-26T11:01:31.491988+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 2,
  "parent_hash": "296e2de0b351a7aef37ac013949bd154a6bd3aac7c606264211743c0e7392779",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:01:30.000000Z",
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
        "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
      }
    },
    "state": "awaiting_investigation"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.491988+00:00",
  "record_hash": "8f985f5f58d5066461f31658dc2c8a2d9c375491ee6406e1d7f7d3d920d1f1f8"
}
```

### 23. 2026-10-26T11:01:31.507952+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 3,
  "parent_hash": "8f985f5f58d5066461f31658dc2c8a2d9c375491ee6406e1d7f7d3d920d1f1f8",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:01:30.000000Z",
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
        "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
      }
    },
    "state": "awaiting_investigation"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.507952+00:00",
  "record_hash": "817e7f46099b68db612698d09d19680dca48ec7fc4e59735ab175b20af7924fc"
}
```

### 24. 2026-10-26T11:01:31.512029+00:00 — command orchestrator_advance

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
      "created_at": "2026-10-26T11:01:31.507952+00:00",
      "customer": "fictional-account",
      "parent_hash": "8f985f5f58d5066461f31658dc2c8a2d9c375491ee6406e1d7f7d3d920d1f1f8",
      "payload": {
        "basis": {
          "as_of": "2026-10-26T11:01:30.000000Z",
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
            "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
          }
        },
        "state": "awaiting_investigation"
      },
      "record_hash": "817e7f46099b68db612698d09d19680dca48ec7fc4e59735ab175b20af7924fc",
      "tenant": "collaboration",
      "version": 3
    },
    "external_execution": "blocked"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.512029+00:00",
  "previous_hash": "6c0d1b56930c3ed8faefe5aa2cb477a09ec133637997de4ede229fbfeeae7a5f",
  "record_hash": "34ea4a72d2726c580eb47478d75fb25a2b2d5b933d9b8909234940186b586955"
}
```

### 25. 2026-10-26T11:01:31.523042+00:00 — C03

Participação: supplied_document_NOT_autonomous

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "c02_run_id": 1,
  "version": 1,
  "parent_hash": null,
  "c02_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1",
  "input_hash": "8be1e8a3e448c938d769e2ddd052f4cc79417cd161baf7ad625ceb305c77fe67",
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.523042+00:00",
  "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
  "declaration": {
    "c02_run_id": 1,
    "customer": "fictional-account",
    "hypotheses": [
      {
        "contrary_refs": [],
        "id": "unconfirmed-prerequisite-hypothesis",
        "statement": "A declared prerequisite may be unmet. Whether this explains the deterioration has not been established.",
        "support_refs": [
          {
            "evidence_id": 13,
            "field": "paused"
          }
        ]
      }
    ],
    "provenance": {
      "recorded_at": "2026-10-25T00:00:00Z",
      "source_ref": "fixture:collaboration:m09-operator-declaration",
      "supplied_by": "synthetic-fixture-author"
    },
    "requirements": [
      {
        "comparison": "eq",
        "criterion_id": "operational-degradation",
        "declaration": "Fictional owner-declared prerequisite: processing must not be paused. This declaration is not causal proof.",
        "expected": false,
        "id": "explicit-unpaused-requirement",
        "selector": {
          "definition_id": "operation-state",
          "field": "paused",
          "kind": "evidence"
        },
        "window": "current"
      }
    ],
    "schema_version": 1,
    "tenant": "collaboration"
  },
  "payload": {
    "algorithm": "c03-structured-v1",
    "tenant": "collaboration",
    "customer": "fictional-account",
    "investigation_version": 1,
    "c02_run_id": 1,
    "c02_run_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1",
    "config_version": 1,
    "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
    "criteria_version": 1,
    "criteria_hash": "ca1c874ceb2f0617fe42d0001a9ef99b6463980ba8aa173bd643a4e49de4fbe0",
    "as_of": "2026-10-26T11:01:30.000000Z",
    "through": 13,
    "classification": "synthetic",
    "operational_state": "inactive",
    "causal_status": "not_established",
    "declaration_provenance": {
      "recorded_at": "2026-10-25T00:00:00Z",
      "source_ref": "fixture:collaboration:m09-operator-declaration",
      "supplied_by": "synthetic-fixture-author"
    },
    "facts": [
      {
        "evidence_id": 1,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "metric",
        "definition_id": "processing-delay",
        "payload": {
          "value": 5
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-metric",
          "external_id": "fictional-processing-delay-0",
          "occurred_at": "2026-10-26T11:01:27.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:26.000000Z",
          "period_end": "2026-10-26T11:01:27.000000Z",
          "actor": "operator",
          "record_hash": "3383ccc7fda9b896d495604320e747df7298e19dd47bf7957cf27779cf92aa89"
        }
      },
      {
        "evidence_id": 2,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "processing-snapshot",
        "payload": {
          "delay_seconds": 5
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-evidence",
          "external_id": "fictional-processing-snapshot-0",
          "occurred_at": "2026-10-26T11:01:27.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:26.000000Z",
          "period_end": "2026-10-26T11:01:27.000000Z",
          "actor": "operator",
          "record_hash": "7173b7ae1e2498cb27fe935c0405f7a476aabd7a0107471eeeb40f97e4ffa6aa"
        }
      },
      {
        "evidence_id": 3,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "value-snapshot",
        "payload": {
          "outcome_count": 6
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:value-definition",
          "external_id": "fictional-value-snapshot-0",
          "occurred_at": "2026-10-26T11:01:27.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:26.000000Z",
          "period_end": "2026-10-26T11:01:27.000000Z",
          "actor": "operator",
          "record_hash": "4a41021179cd2b8bb31e38f72ed0628440000274cae7ee98f440d74b166fc5e5"
        }
      },
      {
        "evidence_id": 4,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "metric",
        "definition_id": "processing-delay",
        "payload": {
          "value": 5
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-metric",
          "external_id": "fictional-processing-delay-1",
          "occurred_at": "2026-10-26T11:01:28.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:27.000000Z",
          "period_end": "2026-10-26T11:01:28.000000Z",
          "actor": "operator",
          "record_hash": "9f7a99eba074ca8ba095cc89b8b6593f4a797770401a11a4ef0edaba318dc7ff"
        }
      },
      {
        "evidence_id": 5,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "processing-snapshot",
        "payload": {
          "delay_seconds": 5
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-evidence",
          "external_id": "fictional-processing-snapshot-1",
          "occurred_at": "2026-10-26T11:01:28.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:27.000000Z",
          "period_end": "2026-10-26T11:01:28.000000Z",
          "actor": "operator",
          "record_hash": "9729bb69ad14d41224a2ac68e1658c99266414e4a1d789be4b87c22f83953985"
        }
      },
      {
        "evidence_id": 6,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "value-snapshot",
        "payload": {
          "outcome_count": 6
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:value-definition",
          "external_id": "fictional-value-snapshot-1",
          "occurred_at": "2026-10-26T11:01:28.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:27.000000Z",
          "period_end": "2026-10-26T11:01:28.000000Z",
          "actor": "operator",
          "record_hash": "cc593bc447aa9f85d890f43185088269974a2908df69169fe624cc85940654d8"
        }
      },
      {
        "evidence_id": 7,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "metric",
        "definition_id": "processing-delay",
        "payload": {
          "value": 20
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-metric",
          "external_id": "fictional-processing-delay-2",
          "occurred_at": "2026-10-26T11:01:29.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:28.000000Z",
          "period_end": "2026-10-26T11:01:29.000000Z",
          "actor": "operator",
          "record_hash": "24dfe732cb5b72356cb562377d2b094aef568d3eb0c23b0c4832e65377292a5d"
        }
      },
      {
        "evidence_id": 8,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "processing-snapshot",
        "payload": {
          "delay_seconds": 20
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-evidence",
          "external_id": "fictional-processing-snapshot-2",
          "occurred_at": "2026-10-26T11:01:29.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:28.000000Z",
          "period_end": "2026-10-26T11:01:29.000000Z",
          "actor": "operator",
          "record_hash": "db7c10a8b15890afa41f1b8ca2a9407108fda66a861fd61d6df869a5ef593051"
        }
      },
      {
        "evidence_id": 9,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "value-snapshot",
        "payload": {
          "outcome_count": 1
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:value-definition",
          "external_id": "fictional-value-snapshot-2",
          "occurred_at": "2026-10-26T11:01:29.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:28.000000Z",
          "period_end": "2026-10-26T11:01:29.000000Z",
          "actor": "operator",
          "record_hash": "ee1cc5b7484c4ebe81a2f9f1a7cead3c695e89706b5c08bab4c4fa3f8dac4a33"
        }
      },
      {
        "evidence_id": 10,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "metric",
        "definition_id": "processing-delay",
        "payload": {
          "value": 20
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-metric",
          "external_id": "fictional-processing-delay-3",
          "occurred_at": "2026-10-26T11:01:30.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:29.000000Z",
          "period_end": "2026-10-26T11:01:30.000000Z",
          "actor": "operator",
          "record_hash": "2ad207996e772dbb68561bd671f59173e4116ffda6b14efbbe9ae99106dde99c"
        }
      },
      {
        "evidence_id": 11,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "processing-snapshot",
        "payload": {
          "delay_seconds": 20
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:processing-evidence",
          "external_id": "fictional-processing-snapshot-3",
          "occurred_at": "2026-10-26T11:01:30.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:29.000000Z",
          "period_end": "2026-10-26T11:01:30.000000Z",
          "actor": "operator",
          "record_hash": "8f2bf96a3ff6f533de9ed325f1e9b01c7ec12005f248b5345bd701fa515d576f"
        }
      },
      {
        "evidence_id": 12,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "value-snapshot",
        "payload": {
          "outcome_count": 1
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:value-definition",
          "external_id": "fictional-value-snapshot-3",
          "occurred_at": "2026-10-26T11:01:30.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": "2026-10-26T11:01:29.000000Z",
          "period_end": "2026-10-26T11:01:30.000000Z",
          "actor": "operator",
          "record_hash": "3d9a580156de966eddef2f8511973105e04e2363d62b7ae48094c1ee16c81134"
        }
      },
      {
        "evidence_id": 13,
        "claim_scope": "recorded_observation",
        "temporal_relation": "at_or_before_c02_as_of",
        "kind": "evidence",
        "definition_id": "operation-state",
        "payload": {
          "paused": true
        },
        "disputed_fields": [],
        "provenance": {
          "tenant": "collaboration",
          "customer": "fictional-account",
          "config_version": 1,
          "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
          "source_ref": "fixture:collaboration:state-definition",
          "external_id": "fictional-paused-observation",
          "occurred_at": "2026-10-26T11:01:30.000000Z",
          "received_at": "2026-10-26T11:01:31.463080Z",
          "period_start": null,
          "period_end": null,
          "actor": "operator",
          "record_hash": "521562f03afb4f2148d4843a8a1aa985880578a2d2f197c54d267f1f9046aab0"
        }
      }
    ],
    "c02_findings": {
      "algorithm": "c02-adaptive-v1",
      "proof_scope": "declared_criteria_and_supplied_evidence",
      "dimensions": {
        "operational_deterioration": {
          "criterion_ids": [
            "operational-degradation"
          ],
          "state": "demonstrated"
        },
        "value_loss": {
          "criterion_ids": [
            "value-loss"
          ],
          "state": "demonstrated"
        }
      },
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
              "end": "2026-10-26T11:01:30.000000Z",
              "evidence_ids": [
                7,
                8,
                10,
                11
              ],
              "issues": [],
              "start": "2026-10-26T11:01:28.000000Z"
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
              "end": "2026-10-26T11:01:28.000000Z",
              "evidence_ids": [
                3,
                6
              ],
              "issues": [],
              "start": "2026-10-26T11:01:26.000000Z"
            },
            "current": {
              "aggregate": {
                "denominator": "1",
                "numerator": "2"
              },
              "contradictions": [],
              "end": "2026-10-26T11:01:30.000000Z",
              "evidence_ids": [
                9,
                12
              ],
              "issues": [],
              "start": "2026-10-26T11:01:28.000000Z"
            }
          }
        }
      ]
    },
    "hypotheses": [
      {
        "contrary_refs": [],
        "id": "unconfirmed-prerequisite-hypothesis",
        "statement": "A declared prerequisite may be unmet. Whether this explains the deterioration has not been established.",
        "support_refs": [
          {
            "evidence_id": 13,
            "field": "paused"
          }
        ],
        "state": "unconfirmed",
        "support_scope": "operator_declared_references_only",
        "causal_status": "not_established",
        "disputed_refs": []
      }
    ],
    "requirements": [
      {
        "requirement_id": "explicit-unpaused-requirement",
        "declared_requirement": {
          "comparison": "eq",
          "criterion_id": "operational-degradation",
          "declaration": "Fictional owner-declared prerequisite: processing must not be paused. This declaration is not causal proof.",
          "expected": false,
          "id": "explicit-unpaused-requirement",
          "selector": {
            "definition_id": "operation-state",
            "field": "paused",
            "kind": "evidence"
          },
          "window": "current"
        },
        "status": "supported",
        "claim_type": "observed_requirement_noncompliance",
        "support_scope": "observed_condition_only",
        "causal_status": "not_established",
        "checked_refs": [
          {
            "evidence_id": 13,
            "field": "paused"
          }
        ],
        "violation_refs": [
          {
            "evidence_id": 13,
            "field": "paused"
          }
        ],
        "compliant_refs": []
      }
    ],
    "supported_impediments": [
      {
        "requirement_id": "explicit-unpaused-requirement",
        "declared_requirement": {
          "comparison": "eq",
          "criterion_id": "operational-degradation",
          "declaration": "Fictional owner-declared prerequisite: processing must not be paused. This declaration is not causal proof.",
          "expected": false,
          "id": "explicit-unpaused-requirement",
          "selector": {
            "definition_id": "operation-state",
            "field": "paused",
            "kind": "evidence"
          },
          "window": "current"
        },
        "status": "supported",
        "claim_type": "observed_requirement_noncompliance",
        "support_scope": "observed_condition_only",
        "causal_status": "not_established",
        "checked_refs": [
          {
            "evidence_id": 13,
            "field": "paused"
          }
        ],
        "violation_refs": [
          {
            "evidence_id": 13,
            "field": "paused"
          }
        ],
        "compliant_refs": []
      }
    ],
    "missing_information": [],
    "analysis_limitations": [],
    "contradictions": []
  }
}
```

### 26. 2026-10-26T11:01:31.524368+00:00 — command C03_declaration

Participação: human_supplied_investigation

```json
{
  "id": 5,
  "operation": "C03_declaration",
  "participation": "human_supplied_investigation",
  "payload": {
    "input_hash": "8be1e8a3e448c938d769e2ddd052f4cc79417cd161baf7ad625ceb305c77fe67",
    "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
    "version": 1
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.524368+00:00",
  "previous_hash": "34ea4a72d2726c580eb47478d75fb25a2b2d5b933d9b8909234940186b586955",
  "record_hash": "f314db731fe74652452db4647b263e0e3ecda25614e089ffc11d2dabdb679624"
}
```

### 27. 2026-10-26T11:01:31.557927+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 4,
  "parent_hash": "817e7f46099b68db612698d09d19680dca48ec7fc4e59735ab175b20af7924fc",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:01:30.000000Z",
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
      "proposal_not_recorded"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
        "id": 1,
        "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
      },
      "c03": {
        "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
        "version": 1
      },
      "c04": {
        "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83"
      }
    },
    "state": "awaiting_ai"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.557927+00:00",
  "record_hash": "56c0ce85aa689ef60d89568f0326b3ef01fb98bc7235731952a74e30ae887b67"
}
```

### 28. 2026-10-26T11:01:31.576629+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 5,
  "parent_hash": "56c0ce85aa689ef60d89568f0326b3ef01fb98bc7235731952a74e30ae887b67",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:01:30.000000Z",
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
      "authorized_ai_not_configured"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
        "id": 1,
        "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
      },
      "c03": {
        "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
        "version": 1
      },
      "c04": {
        "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83"
      }
    },
    "state": "awaiting_ai"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.576629+00:00",
  "record_hash": "3f68d3bdee5604784475cddb3693a26b0c0fe6597d2a7beb918afe6473be63c2"
}
```

### 29. 2026-10-26T11:01:31.580220+00:00 — command orchestrator_advance

Participação: automatic_bounded_processing

```json
{
  "id": 6,
  "operation": "orchestrator_advance",
  "participation": "automatic_bounded_processing",
  "payload": {
    "ai_kind": "unavailable",
    "checkpoint": {
      "actor": "operator",
      "case_id": "observed-cycle",
      "created_at": "2026-10-26T11:01:31.576629+00:00",
      "customer": "fictional-account",
      "parent_hash": "56c0ce85aa689ef60d89568f0326b3ef01fb98bc7235731952a74e30ae887b67",
      "payload": {
        "basis": {
          "as_of": "2026-10-26T11:01:30.000000Z",
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
          "authorized_ai_not_configured"
        ],
        "core_transition_authorized": false,
        "operational_state": "inactive",
        "real_recovery_demonstrated": false,
        "refs": {
          "c02": {
            "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
            "id": 1,
            "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
          },
          "c03": {
            "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
            "version": 1
          },
          "c04": {
            "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83"
          }
        },
        "state": "awaiting_ai"
      },
      "record_hash": "3f68d3bdee5604784475cddb3693a26b0c0fe6597d2a7beb918afe6473be63c2",
      "tenant": "collaboration",
      "version": 5
    },
    "external_execution": "blocked"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.580220+00:00",
  "previous_hash": "f314db731fe74652452db4647b263e0e3ecda25614e089ffc11d2dabdb679624",
  "record_hash": "66ee58b806809d76bf3cd65ed07f382736a1fc4b2b0ba361d286b4b72af6cc05"
}
```

### 30. 2026-10-26T11:01:31.624794+00:00 — command orchestrator_advance

Participação: automatic_bounded_processing

```json
{
  "id": 7,
  "operation": "orchestrator_advance",
  "participation": "automatic_bounded_processing",
  "payload": {
    "ai_kind": "unavailable",
    "checkpoint": {
      "actor": "operator",
      "case_id": "observed-cycle",
      "created_at": "2026-10-26T11:01:31.576629+00:00",
      "customer": "fictional-account",
      "parent_hash": "56c0ce85aa689ef60d89568f0326b3ef01fb98bc7235731952a74e30ae887b67",
      "payload": {
        "basis": {
          "as_of": "2026-10-26T11:01:30.000000Z",
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
          "authorized_ai_not_configured"
        ],
        "core_transition_authorized": false,
        "operational_state": "inactive",
        "real_recovery_demonstrated": false,
        "refs": {
          "c02": {
            "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
            "id": 1,
            "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
          },
          "c03": {
            "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
            "version": 1
          },
          "c04": {
            "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83"
          }
        },
        "state": "awaiting_ai"
      },
      "record_hash": "3f68d3bdee5604784475cddb3693a26b0c0fe6597d2a7beb918afe6473be63c2",
      "tenant": "collaboration",
      "version": 5
    },
    "external_execution": "blocked"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.624794+00:00",
  "previous_hash": "66ee58b806809d76bf3cd65ed07f382736a1fc4b2b0ba361d286b4b72af6cc05",
  "record_hash": "38ad09ac949fed8ff43c92663c2155ebe15377a51f9b590ec9843d59578fb884"
}
```

### 31. 2026-10-26T11:01:31.645696+00:00 — C04 request

Participação: explicit_fixture_or_authorized_provider_request

```json
{
  "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.645696+00:00",
  "record_hash": "c2aa5fafbb5c5e740a365a72c22f3522cc6dbcea33d31d26b4c8be09db83261c"
}
```

### 32. 2026-10-26T11:01:31.653229+00:00 — C04 result

Participação: test_fixture_NOT_AI

```json
{
  "request": {
    "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
    "c02_run_id": 1,
    "c03_version": 1,
    "context_hash": "dbdffbb76577fe5be81b8a66174282444d301c711b3e00472f63005ff30d62a7",
    "actor": "operator",
    "created_at": "2026-10-26T11:01:31.645696+00:00",
    "record_hash": "c2aa5fafbb5c5e740a365a72c22f3522cc6dbcea33d31d26b4c8be09db83261c"
  },
  "result": {
    "tenant": "collaboration",
    "customer": "fictional-account",
    "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
    "receipt": {
      "completion_received": true,
      "failure": null,
      "inference_kind": "test_fixture",
      "post_context_hash": "dbdffbb76577fe5be81b8a66174282444d301c711b3e00472f63005ff30d62a7",
      "post_current_heads": {
        "c02_run_id": 1,
        "c03_version": 1,
        "config_version": 1,
        "criteria_version": 1,
        "evidence_id": 13
      },
      "reported_model": "explicit-fixture-not-ai",
      "requested_model": "explicit-fixture-not-ai",
      "response_id": "supplied-fixture",
      "revalidation": "matched"
    },
    "response_hash": "5817a722832a056f6563c741b4ae3f7958588e592c918e5b87d7e48f82f67240",
    "payload": {
      "authorization": "not_granted",
      "causal_status": "not_established",
      "condition_checks": [
        {
          "condition": {
            "evidence_ref": "operation-state",
            "field": "paused",
            "operator": "eq",
            "value": true
          },
          "fact_refs": [
            {
              "evidence_id": 13,
              "field": "paused"
            }
          ],
          "state": "satisfied"
        }
      ],
      "execution_authorized": false,
      "human_review_required": true,
      "model_response": {
        "analysis_limitation_refs": [],
        "context_hash": "dbdffbb76577fe5be81b8a66174282444d301c711b3e00472f63005ff30d62a7",
        "contradiction_refs": [],
        "hypothesis_reviews": [
          {
            "contrary_refs": [],
            "disposition": "retain_unconfirmed",
            "hypothesis_id": "unconfirmed-prerequisite-hypothesis",
            "support_refs": [
              {
                "evidence_id": 13,
                "field": "paused"
              }
            ]
          }
        ],
        "impediment_refs": [
          "explicit-unpaused-requirement"
        ],
        "missing_information_refs": [],
        "recommendation": {
          "capability_id": "reopen-delivery-queue",
          "criterion_refs": [
            "operational-degradation",
            "value-loss"
          ],
          "evidence_refs": [
            {
              "evidence_id": 13,
              "field": "paused"
            }
          ],
          "kind": "action_proposal",
          "reason_code": "catalogue_match"
        },
        "schema_version": 1
      },
      "operational_state": "inactive",
      "reason_codes": [
        "declared_conditions_and_evidence_match"
      ],
      "status": "proposal_validated",
      "validated_capability_id": "reopen-delivery-queue",
      "validator": "c04-grounded-v1",
      "verification_plan": {
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
      },
      "verification_status": "not_performed"
    },
    "created_at": "2026-10-26T11:01:31.653229+00:00",
    "record_hash": "b6ca33398d86dd8c42a9531b3752366c7aa2ec1b651171d01b93162cd3f08685"
  }
}
```

### 33. 2026-10-26T11:01:31.660007+00:00 — command C04_supplied_fixture

Participação: test_fixture_NOT_AI

```json
{
  "id": 8,
  "operation": "C04_supplied_fixture",
  "participation": "test_fixture_NOT_AI",
  "payload": {
    "input_hash": "5817a722832a056f6563c741b4ae3f7958588e592c918e5b87d7e48f82f67240",
    "result": {
      "created_at": "2026-10-26T11:01:31.653229+00:00",
      "customer": "fictional-account",
      "payload": {
        "authorization": "not_granted",
        "causal_status": "not_established",
        "condition_checks": [
          {
            "condition": {
              "evidence_ref": "operation-state",
              "field": "paused",
              "operator": "eq",
              "value": true
            },
            "fact_refs": [
              {
                "evidence_id": 13,
                "field": "paused"
              }
            ],
            "state": "satisfied"
          }
        ],
        "execution_authorized": false,
        "human_review_required": true,
        "model_response": {
          "analysis_limitation_refs": [],
          "context_hash": "dbdffbb76577fe5be81b8a66174282444d301c711b3e00472f63005ff30d62a7",
          "contradiction_refs": [],
          "hypothesis_reviews": [
            {
              "contrary_refs": [],
              "disposition": "retain_unconfirmed",
              "hypothesis_id": "unconfirmed-prerequisite-hypothesis",
              "support_refs": [
                {
                  "evidence_id": 13,
                  "field": "paused"
                }
              ]
            }
          ],
          "impediment_refs": [
            "explicit-unpaused-requirement"
          ],
          "missing_information_refs": [],
          "recommendation": {
            "capability_id": "reopen-delivery-queue",
            "criterion_refs": [
              "operational-degradation",
              "value-loss"
            ],
            "evidence_refs": [
              {
                "evidence_id": 13,
                "field": "paused"
              }
            ],
            "kind": "action_proposal",
            "reason_code": "catalogue_match"
          },
          "schema_version": 1
        },
        "operational_state": "inactive",
        "reason_codes": [
          "declared_conditions_and_evidence_match"
        ],
        "status": "proposal_validated",
        "validated_capability_id": "reopen-delivery-queue",
        "validator": "c04-grounded-v1",
        "verification_plan": {
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
        },
        "verification_status": "not_performed"
      },
      "receipt": {
        "completion_received": true,
        "failure": null,
        "inference_kind": "test_fixture",
        "post_context_hash": "dbdffbb76577fe5be81b8a66174282444d301c711b3e00472f63005ff30d62a7",
        "post_current_heads": {
          "c02_run_id": 1,
          "c03_version": 1,
          "config_version": 1,
          "criteria_version": 1,
          "evidence_id": 13
        },
        "reported_model": "explicit-fixture-not-ai",
        "requested_model": "explicit-fixture-not-ai",
        "response_id": "supplied-fixture",
        "revalidation": "matched"
      },
      "record_hash": "b6ca33398d86dd8c42a9531b3752366c7aa2ec1b651171d01b93162cd3f08685",
      "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
      "response_hash": "5817a722832a056f6563c741b4ae3f7958588e592c918e5b87d7e48f82f67240",
      "tenant": "collaboration"
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.660007+00:00",
  "previous_hash": "38ad09ac949fed8ff43c92663c2155ebe15377a51f9b590ec9843d59578fb884",
  "record_hash": "14e4e01c6790ca3a82d226db0f983809b039d5fa2de6ca729e34b1fe14a49a8c"
}
```

### 34. 2026-10-26T11:01:31.697915+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 6,
  "parent_hash": "3f68d3bdee5604784475cddb3693a26b0c0fe6597d2a7beb918afe6473be63c2",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:01:30.000000Z",
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
      "intent_not_prepared"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
        "id": 1,
        "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
      },
      "c03": {
        "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
        "version": 1
      },
      "c04": {
        "inference_kind": "test_fixture",
        "record_hash": "b6ca33398d86dd8c42a9531b3752366c7aa2ec1b651171d01b93162cd3f08685",
        "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
        "status": "proposal_validated"
      },
      "c05": {
        "execution_id": "orch-d04df82ff61664bdd9709b06d2e0f4c5a3b0172ac557223fbc8d012aa7"
      }
    },
    "state": "awaiting_execution"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.697915+00:00",
  "record_hash": "ee323923c511b96bdb7e30d75fbe7372527dfd6c04d68869edc25aa3b53c2774"
}
```

### 35. 2026-10-26T11:01:31.744664+00:00 — C05 prepare

Participação: automatic_controlled_synthetic_execution

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "execution_id": "orch-d04df82ff61664bdd9709b06d2e0f4c5a3b0172ac557223fbc8d012aa7",
  "payload": {
    "actor": "operator",
    "created_at": "2026-10-26T11:01:31.744664+00:00",
    "identity_basis": "trusted_local_core_principal",
    "operation": "prepare",
    "reason_code": null,
    "status": "prepared"
  },
  "previous_hash": "",
  "record_hash": "4d52621608214b7575ae0d1239ad46f0587dcb15462fbd227a707d42af1a3d08"
}
```

### 36. 2026-10-26T11:01:31.753244+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 7,
  "parent_hash": "ee323923c511b96bdb7e30d75fbe7372527dfd6c04d68869edc25aa3b53c2774",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:01:30.000000Z",
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
      "explicit_human_approval_required"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
        "id": 1,
        "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
      },
      "c03": {
        "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
        "version": 1
      },
      "c04": {
        "inference_kind": "test_fixture",
        "record_hash": "b6ca33398d86dd8c42a9531b3752366c7aa2ec1b651171d01b93162cd3f08685",
        "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
        "status": "proposal_validated"
      },
      "c05": {
        "execution_id": "orch-d04df82ff61664bdd9709b06d2e0f4c5a3b0172ac557223fbc8d012aa7",
        "intent_hash": "324b8d2393c87abe7a58100dbec1e9026b757fa9769412426c7c2b26231f32dc",
        "state": "awaiting_human_approval"
      }
    },
    "state": "awaiting_approval"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.753244+00:00",
  "record_hash": "e540dbced16064e4dce630fc06aa09a6675b5af94b2db2733542bbbb85e0806b"
}
```

### 37. 2026-10-26T11:01:31.756732+00:00 — command orchestrator_advance

Participação: automatic_bounded_processing

```json
{
  "id": 9,
  "operation": "orchestrator_advance",
  "participation": "automatic_bounded_processing",
  "payload": {
    "ai_kind": "unavailable",
    "checkpoint": {
      "actor": "operator",
      "case_id": "observed-cycle",
      "created_at": "2026-10-26T11:01:31.753244+00:00",
      "customer": "fictional-account",
      "parent_hash": "ee323923c511b96bdb7e30d75fbe7372527dfd6c04d68869edc25aa3b53c2774",
      "payload": {
        "basis": {
          "as_of": "2026-10-26T11:01:30.000000Z",
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
          "explicit_human_approval_required"
        ],
        "core_transition_authorized": false,
        "operational_state": "inactive",
        "real_recovery_demonstrated": false,
        "refs": {
          "c02": {
            "basis": "80b920d3e9b9d68e8f1942edb70bd5fb412f6a57be5eafac084f53ae6c9760dd",
            "id": 1,
            "record_hash": "3f7fa7dca1198a1663c378ec493cd0c20f416aac5db4bee1868ba8c079efb8a1"
          },
          "c03": {
            "record_hash": "bce48f60af19e4e16905bfbce3f141ebf4b3f30810108a84f02a7f7357ad4e7a",
            "version": 1
          },
          "c04": {
            "inference_kind": "test_fixture",
            "record_hash": "b6ca33398d86dd8c42a9531b3752366c7aa2ec1b651171d01b93162cd3f08685",
            "request_id": "orch-38d0e2df161339c3ceab2a000b5b9f618e33c9a31cb5f72cd3ca33ab83",
            "status": "proposal_validated"
          },
          "c05": {
            "execution_id": "orch-d04df82ff61664bdd9709b06d2e0f4c5a3b0172ac557223fbc8d012aa7",
            "intent_hash": "324b8d2393c87abe7a58100dbec1e9026b757fa9769412426c7c2b26231f32dc",
            "state": "awaiting_human_approval"
          }
        },
        "state": "awaiting_approval"
      },
      "record_hash": "e540dbced16064e4dce630fc06aa09a6675b5af94b2db2733542bbbb85e0806b",
      "tenant": "collaboration",
      "version": 7
    },
    "external_execution": "blocked"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:01:31.756732+00:00",
  "previous_hash": "14e4e01c6790ca3a82d226db0f983809b039d5fa2de6ca729e34b1fe14a49a8c",
  "record_hash": "5662ed9e4aa8df7634f50b2647d9ed9ff741471eac53dec1ff7ec731cf89a14c"
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
