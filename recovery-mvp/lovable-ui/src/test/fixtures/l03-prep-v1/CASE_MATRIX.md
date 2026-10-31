# L03-PREP v1 — matriz dos casos capturados

Cada linha referencia um caso real sanitizado em capture.json. PASS significa que
a suite passou validação OpenAPI/contrato, comparação com nova execução e os gates
de permissões/semântica; HTTP de erro esperado também é um caso PASS. Esta tabela
é derivada das fixtures e não substitui o resultado do CI no commit entregue.

| Caso | Método | HTTP | Recibo F06 | Resultado de negócio | Gate esperado |
|---|---|---|---|---|---|
| `authentication-required-401` | GET | 401 | — | — | PASS |
| `post-sessions-01` | POST | 201 | — | — | PASS |
| `session-reader-1` | GET | 200 | — | — | PASS |
| `post-sessions-02` | POST | 201 | — | — | PASS |
| `session-bob-1` | GET | 200 | — | — | PASS |
| `post-sessions-03` | POST | 201 | — | — | PASS |
| `session-alice-1` | GET | 200 | — | — | PASS |
| `journey-initial` | GET | 200 | — | — | PASS |
| `post-sessions-04` | POST | 201 | — | — | PASS |
| `session-alice-2` | GET | 200 | — | — | PASS |
| `post-sessions-05` | POST | 201 | — | — | PASS |
| `session-reviewer-1` | GET | 200 | — | — | PASS |
| `append_value-01` | POST | 200 | completed | — | PASS |
| `journey-after-append_value-1` | GET | 200 | — | — | PASS |
| `append_value-02` | POST | 200 | completed | — | PASS |
| `append_value-03` | POST | 200 | completed | — | PASS |
| `append_value-04` | POST | 200 | completed | — | PASS |
| `detect-01` | POST | 200 | completed | deterioracao_demonstrada | PASS |
| `journey-after-detect-1` | GET | 200 | — | — | PASS |
| `open_investigation-01` | POST | 200 | completed | — | PASS |
| `journey-after-open_investigation-1` | GET | 200 | — | — | PASS |
| `append_investigation-01` | POST | 200 | completed | — | PASS |
| `append_investigation-02` | POST | 200 | completed | — | PASS |
| `investigate-01` | POST | 200 | completed | inconclusivo | PASS |
| `journey-after-investigate-1` | GET | 200 | — | — | PASS |
| `intervene-01` | POST | 200 | completed | blocked | PASS |
| `journey-after-intervene-1` | GET | 200 | — | — | PASS |
| `append_investigation-03` | POST | 200 | completed | — | PASS |
| `append_investigation-04` | POST | 200 | completed | — | PASS |
| `append_investigation-05` | POST | 200 | completed | — | PASS |
| `investigate-02` | POST | 200 | completed | impedimento_demonstrado | PASS |
| `journey-after-investigate-2` | GET | 200 | — | — | PASS |
| `intervene-02` | POST | 200 | completed | executed | PASS |
| `journey-after-intervene-2` | GET | 200 | — | — | PASS |
| `get-journey-09` | GET | 200 | — | — | PASS |
| `append_value-05` | POST | 200 | completed | — | PASS |
| `append_value-06` | POST | 200 | completed | — | PASS |
| `append_value-07` | POST | 200 | completed | — | PASS |
| `plan_recovery-01` | POST | 200 | completed | — | PASS |
| `evaluate_recovery-01` | POST | 200 | completed | resultado_inconclusivo | PASS |
| `journey-after-evaluate_recovery-1` | GET | 200 | — | — | PASS |
| `append_value-08` | POST | 200 | completed | — | PASS |
| `evaluate_recovery-02` | POST | 200 | completed | recuperacao_completa | PASS |
| `journey-after-evaluate_recovery-2` | GET | 200 | — | — | PASS |
| `directory-alice` | GET | 200 | — | — | PASS |
| `directory-reviewer` | GET | 200 | — | — | PASS |
| `directory-reader` | GET | 200 | — | — | PASS |
| `directory-bob` | GET | 200 | — | — | PASS |
| `bob-denied-company-a-403` | GET | 403 | — | — | PASS |
| `alice-denied-company-b-403` | GET | 403 | — | — | PASS |
| `reader-denied-client-403` | GET | 403 | — | — | PASS |
| `reader-denied-intervention-403` | POST | 403 | — | — | PASS |
| `reviewer-denied-intervention-403` | POST | 403 | — | — | PASS |
| `intervention-idempotent-replay` | POST | 200 | completed | executed | PASS |
| `idempotency-conflict-409` | POST | 409 | — | — | PASS |
| `engine-error-receipt-422` | POST | 422 | error | — | PASS |
| `invalid-envelope-422` | POST | 422 | — | — | PASS |
| `unknown-route-404` | GET | 404 | — | — | PASS |
| `journey-with-error-receipt` | GET | 200 | — | — | PASS |
| `changed-scope-invalidates-session-401` | GET | 401 | — | — | PASS |
| `post-sessions-06` | POST | 201 | — | — | PASS |
| `session-reader-2` | GET | 200 | — | — | PASS |
| `directory-page-1` | GET | 200 | — | — | PASS |
| `directory-page-2` | GET | 200 | — | — | PASS |
| `directory-page-empty` | GET | 200 | — | — | PASS |
| `directory-invalid-limit-422` | GET | 422 | — | — | PASS |
| `logout-204` | DELETE | 204 | — | — | PASS |
| `revoked-session-401` | GET | 401 | — | — | PASS |
| `database-unavailable-503` | GET | 503 | — | — | PASS |
| `api-unavailable-503` | GET | 503 | — | — | PASS |
| `network-failure` | GET | sem HTTP (connection_refused) | — | — | PASS |

