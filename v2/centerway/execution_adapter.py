"""C05 adapter contract only. No configured connector or runtime test implementation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionReceipt:
    # Adapter-reported test outcome, never proof of operational/value recovery.
    status: str  # test_applied | failed_no_effect | uncertain
    receipt_id: str
    before_revision: str
    after_revision: str | None


class ExecutionAdapter:
    """Trusted local injection only; no class names, URLs, commands or secrets from AI.

    observe(binding) returns a scoped, versioned point snapshot. apply(key,binding,
    snapshot) MUST atomically compare revision/conditions and persist the key with
    its test effect. Retrying after an unknown outcome is forbidden by this engine.
    No adapter is installed by default; only explicit test adapters are accepted
    in this mission, only with synthetic contracts and outside production.
    """
    def descriptor(self): raise NotImplementedError
    def observe(self, binding): raise NotImplementedError
    def apply(self, execution_key, binding, snapshot): raise NotImplementedError
