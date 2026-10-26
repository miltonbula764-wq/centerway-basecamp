# CENTERWAY — execução local observável

**SOMENTE ENSAIO SINTÉTICO. Uma fixture C04 não comprova inferência real; efeitos/resultados sintéticos não comprovam execução externa ou recuperação real.**

Gerado: 2026-10-26T11:20:45.653648+00:00

## Resultado efetivamente calculado

```json
{
  "scenario": "insufficient",
  "classification": "synthetic_test_only",
  "case_state": "awaiting_data",
  "blockers": [
    "insufficient_detection"
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

### 1. 2026-10-26T11:03:46.730369+00:00 — M06

Participação: supplied_synthetic_contract

```json
{
  "tenant": "collaboration",
  "version": 1,
  "parent_hash": null,
  "content_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.730369+00:00",
  "record_hash": "18d3874d46c37be9704209d6dc9d95995c387a4105111b704c9d5c13947f07aa",
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

### 2. 2026-10-26T11:03:46.736324+00:00 — C02 criteria

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
  "created_at": "2026-10-26T11:03:46.736324+00:00",
  "record_hash": "74efe77fa8dc094f2a532daab83888302a3e7fd128cec9ada81ff1171f74b814",
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

### 3. 2026-10-26T11:03:46.748284+00:00 — command initialize

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
      "initial-evidence.json": "186ed47cb63b99ac5af07dc7073c193a84a723dfe9c4dd52e081c7457ae0640a",
      "investigation.json": "8be1e8a3e448c938d769e2ddd052f4cc79417cd161baf7ad625ceb305c77fe67"
    },
    "profile": {
      "as_of": "2026-10-26T11:03:45.000000Z",
      "case_id": "observed-cycle",
      "classification": "synthetic",
      "customer": "fictional-account",
      "fault": "none",
      "operator": "operator",
      "real_recovery_demonstrated": false,
      "scenario": "insufficient",
      "tenant": "collaboration",
      "usage_step": 2
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.748284+00:00",
  "previous_hash": null,
  "record_hash": "9435b304bf14d67065d89093d87b8f3c71c7d0c725d240ba394fa7e011f4c84a"
}
```

### 4. 2026-10-26T11:03:46.811635+00:00 — command login

Participação: human_session

```json
{
  "id": 2,
  "operation": "login",
  "participation": "human_session",
  "payload": {
    "expires_at": "2026-10-26T12:03:46.810324+00:00",
    "user": "operator"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.811635+00:00",
  "previous_hash": "9435b304bf14d67065d89093d87b8f3c71c7d0c725d240ba394fa7e011f4c84a",
  "record_hash": "3a1bbea1e372256a650dab9a688bf442df0aef7e5d10227019e85649fa9e8316"
}
```

### 5. 2026-10-26T11:03:46.814869Z — M07

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
  "occurred_at": "2026-10-26T11:03:42.000000Z",
  "period_start": "2026-10-26T11:03:41.000000Z",
  "period_end": "2026-10-26T11:03:42.000000Z",
  "payload": {
    "value": 5
  },
  "content_hash": "e38dbb0d0e41ba1aeb477529f251f7469a3fa3199a49bfea57ea3c52d3001d92",
  "fact_hash": "bb04cd98e1d54b611c684ea4507bb18ebef304d648d53ce099743138d9a68331",
  "actor": "operator",
  "received_at": "2026-10-26T11:03:46.814869Z",
  "record_hash": "e036b62d50298bc6f4094d8331257d885d6288664ae9fa59ad04eeb04c5d6b5f"
}
```

### 6. 2026-10-26T11:03:46.816753+00:00 — command M07_ingest

Participação: human_supplied_synthetic_evidence

```json
{
  "id": 3,
  "operation": "M07_ingest",
  "participation": "human_supplied_synthetic_evidence",
  "payload": {
    "input_hash": "186ed47cb63b99ac5af07dc7073c193a84a723dfe9c4dd52e081c7457ae0640a",
    "result": {
      "batch_id": 1,
      "classification": "synthetic",
      "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
      "config_version": 1,
      "customer": "fictional-account",
      "duplicates": 0,
      "inserted": 1,
      "operational_state": "inactive",
      "record_ids": [
        1
      ],
      "reused": false,
      "tenant": "collaboration"
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.816753+00:00",
  "previous_hash": "3a1bbea1e372256a650dab9a688bf442df0aef7e5d10227019e85649fa9e8316",
  "record_hash": "cb3c76ef834e00e37a9fc7415cfbb745516788fbd473e3593cd4a418f538f326"
}
```

### 7. 2026-10-26T11:03:46.820723+00:00 — M14 opening

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
  "created_at": "2026-10-26T11:03:46.820723+00:00",
  "record_hash": "a116b1f45501e9c2f35acd695cd83b34d46e4a82c63c79d1a8ec375ed16e8a81"
}
```

### 8. 2026-10-26T11:03:46.824937+00:00 — orchestrator checkpoint

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
  "created_at": "2026-10-26T11:03:46.824937+00:00",
  "record_hash": "86bed2d39c85be7c25b1460649381954162bbe8a893b8a12e4e90c27dcf0fb21"
}
```

### 9. 2026-10-26T11:03:46.839105+00:00 — C02

Participação: automatic_deterministic_assessment

```json
{
  "id": 1,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "criteria_version": 1,
  "request_hash": "006c39a57c7050b3a4e01bc658e6aef7213094321cf21cef4359253db925d97d",
  "payload": {
    "algorithm": "c02-adaptive-v1",
    "as_of": "2026-10-26T11:03:45.000000Z",
    "classification": "synthetic",
    "config_hash": "9a95e41d08fde8f37bf70cc0fd39369cccfa13aa83b2b2cc85cf0d103169bde7",
    "config_version": 1,
    "criteria_hash": "ca1c874ceb2f0617fe42d0001a9ef99b6463980ba8aa173bd643a4e49de4fbe0",
    "criteria_results": [
      {
        "contradictions": [],
        "criterion_id": "operational-degradation",
        "dimension": "operational",
        "issues": [
          {
            "code": "missing_samples",
            "definition_id": "processing-delay",
            "kind": "metric",
            "missing_buckets": 2,
            "window": "current"
          },
          {
            "code": "missing_samples",
            "definition_id": "processing-snapshot",
            "kind": "evidence",
            "missing_buckets": 2,
            "window": "current"
          }
        ],
        "measured": null,
        "state": "insufficient",
        "windows": {
          "current": {
            "aggregate": null,
            "contradictions": [],
            "end": "2026-10-26T11:03:45.000000Z",
            "evidence_ids": [],
            "issues": [
              {
                "code": "missing_samples",
                "definition_id": "processing-delay",
                "kind": "metric",
                "missing_buckets": 2
              },
              {
                "code": "missing_samples",
                "definition_id": "processing-snapshot",
                "kind": "evidence",
                "missing_buckets": 2
              }
            ],
            "start": "2026-10-26T11:03:43.000000Z"
          }
        }
      },
      {
        "contradictions": [],
        "criterion_id": "value-loss",
        "dimension": "value",
        "issues": [
          {
            "code": "missing_samples",
            "definition_id": "value-snapshot",
            "kind": "evidence",
            "missing_buckets": 2,
            "window": "current"
          },
          {
            "code": "missing_samples",
            "definition_id": "value-snapshot",
            "kind": "evidence",
            "missing_buckets": 2,
            "window": "baseline"
          }
        ],
        "measured": null,
        "state": "insufficient",
        "windows": {
          "baseline": {
            "aggregate": null,
            "contradictions": [],
            "end": "2026-10-26T11:03:43.000000Z",
            "evidence_ids": [],
            "issues": [
              {
                "code": "missing_samples",
                "definition_id": "value-snapshot",
                "kind": "evidence",
                "missing_buckets": 2
              }
            ],
            "start": "2026-10-26T11:03:41.000000Z"
          },
          "current": {
            "aggregate": null,
            "contradictions": [],
            "end": "2026-10-26T11:03:45.000000Z",
            "evidence_ids": [],
            "issues": [
              {
                "code": "missing_samples",
                "definition_id": "value-snapshot",
                "kind": "evidence",
                "missing_buckets": 2
              }
            ],
            "start": "2026-10-26T11:03:43.000000Z"
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
        "record_hash": "e036b62d50298bc6f4094d8331257d885d6288664ae9fa59ad04eeb04c5d6b5f"
      }
    ],
    "operational_deterioration": {
      "criterion_ids": [
        "operational-degradation"
      ],
      "state": "insufficient"
    },
    "operational_state": "inactive",
    "proof_scope": "declared_criteria_and_supplied_evidence",
    "tenant": "collaboration",
    "through": 1,
    "value_loss": {
      "criterion_ids": [
        "value-loss"
      ],
      "state": "insufficient"
    }
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.839105+00:00",
  "record_hash": "a359a58db1953eb50eb2cf871e9ff334d29f6f30375ba7ff2aa3bec5d2bbba14",
  "reused": true
}
```

### 10. 2026-10-26T11:03:46.841594+00:00 — orchestrator checkpoint

Participação: automatic_state_and_blockers

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "case_id": "observed-cycle",
  "version": 2,
  "parent_hash": "86bed2d39c85be7c25b1460649381954162bbe8a893b8a12e4e90c27dcf0fb21",
  "payload": {
    "basis": {
      "as_of": "2026-10-26T11:03:45.000000Z",
      "source_hash": "bfb3ff4b3e17e7d50608a3b3750db1c679cb4510f9fb911b0e1d7ebafc19c59a",
      "source_heads": {
        "config_version": 1,
        "criteria_version": 1,
        "eligible_ids": [
          1
        ],
        "through": 1
      }
    },
    "blockers": [
      "insufficient_detection"
    ],
    "core_transition_authorized": false,
    "operational_state": "inactive",
    "real_recovery_demonstrated": false,
    "refs": {
      "c02": {
        "basis": "bfb3ff4b3e17e7d50608a3b3750db1c679cb4510f9fb911b0e1d7ebafc19c59a",
        "id": 1,
        "record_hash": "a359a58db1953eb50eb2cf871e9ff334d29f6f30375ba7ff2aa3bec5d2bbba14"
      }
    },
    "state": "awaiting_data"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.841594+00:00",
  "record_hash": "0ee39aa01e49b538781c7cd74686d975aeb74aa47388f59e679bcd62ffb9ad9e"
}
```

### 11. 2026-10-26T11:03:46.845929+00:00 — command orchestrator_advance

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
      "created_at": "2026-10-26T11:03:46.841594+00:00",
      "customer": "fictional-account",
      "parent_hash": "86bed2d39c85be7c25b1460649381954162bbe8a893b8a12e4e90c27dcf0fb21",
      "payload": {
        "basis": {
          "as_of": "2026-10-26T11:03:45.000000Z",
          "source_hash": "bfb3ff4b3e17e7d50608a3b3750db1c679cb4510f9fb911b0e1d7ebafc19c59a",
          "source_heads": {
            "config_version": 1,
            "criteria_version": 1,
            "eligible_ids": [
              1
            ],
            "through": 1
          }
        },
        "blockers": [
          "insufficient_detection"
        ],
        "core_transition_authorized": false,
        "operational_state": "inactive",
        "real_recovery_demonstrated": false,
        "refs": {
          "c02": {
            "basis": "bfb3ff4b3e17e7d50608a3b3750db1c679cb4510f9fb911b0e1d7ebafc19c59a",
            "id": 1,
            "record_hash": "a359a58db1953eb50eb2cf871e9ff334d29f6f30375ba7ff2aa3bec5d2bbba14"
          }
        },
        "state": "awaiting_data"
      },
      "record_hash": "0ee39aa01e49b538781c7cd74686d975aeb74aa47388f59e679bcd62ffb9ad9e",
      "tenant": "collaboration",
      "version": 2
    },
    "external_execution": "blocked"
  },
  "actor": "operator",
  "created_at": "2026-10-26T11:03:46.845929+00:00",
  "previous_hash": "cb3c76ef834e00e37a9fc7415cfbb745516788fbd473e3593cd4a418f538f326",
  "record_hash": "9db6a2240154bc92daf2cef388c3912e598157621e002368b5334c8177534aa0"
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
