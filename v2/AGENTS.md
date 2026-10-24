# CENTERWAY V2

The user authorized an independent rebuild for Mission 01. This directory is a new
Python/SQLite sandbox and does not use the historical application's components,
Supabase schema, RPCs, providers, or build tools. Root rules specific to those
historical components do not describe this runtime. Never publish or merge to main.

- Run `python -m unittest discover -s tests -v` from v2.
- Permissions, evidence, decisions and effects are server owned; the browser passes IDs only.
- Keep tenant predicates in all scoped database operations. Never reuse browser role claims.
- Sandbox effects, execution uniqueness and audit history commit atomically.
- Identify simulated decisions and simulated usage explicitly; never label them real AI or production recovery.
