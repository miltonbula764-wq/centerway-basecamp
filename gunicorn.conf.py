"""Repository-root entrypoint for the isolated CENTERWAY Render profile."""
from pathlib import Path
import runpy

_config = Path(__file__).resolve().parent / 'recovery-mvp' / 'managed' / 'gunicorn.conf.py'
globals().update({k:v for k,v in runpy.run_path(str(_config)).items() if not k.startswith('_')})
