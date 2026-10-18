"""Stage the existing application without .env and mount a new disposable MVP stack."""
from pathlib import Path
import subprocess
import tempfile
from runtime import provision, stage_source

root = Path(__file__).resolve().parents[2]
stage = Path(tempfile.mkdtemp(prefix='centerway-mvp-')) / 'app'
stage_source(root, stage)
print('Isolated working copy:', stage, flush=True)
env = provision(stage)
print('\nOpen http://127.0.0.1:5173/app/casos\nOnly synthetic data in a new local database.', flush=True)
print('Demo accounts and temporary passwords are in the PRIVATE local file:', stage / 'e2e/private/mvp-users.json', flush=True)
print('Stop the app with Ctrl+C; remove ONLY this stack with python3 scripts/mvp/stop-local.py', flush=True)
subprocess.run(['bun', 'run', 'dev', '--host', '127.0.0.1', '--port', '5173'], cwd=stage, env=env, check=True)
