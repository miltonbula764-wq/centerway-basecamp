"""Render-only entrypoint. Existing direct-TLS/local entrypoints are unchanged.

Render terminates TLS and redirects HTTP at its edge. Trust that deployment
boundary, NOT client Forwarded/X-Forwarded-* headers. Do not use on a VM or
behind another proxy; there is deliberately no generic proxy-trust setting.
"""
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import create_app


class RenderEdge:
    def __init__(self, app, hostname):
        if not re.fullmatch(r'[a-z0-9-]+\.onrender\.com', hostname):
            raise ValueError('Render assigned hostname required')
        self.app, self.hostname = app, hostname

    def __call__(self, environ, start_response):
        # The platform can probe internally without a public Host. No DB access.
        if environ.get('PATH_INFO') == '/health' and environ.get('REQUEST_METHOD') == 'GET':
            start_response('200 OK', [('Content-Type','application/json'),('Cache-Control','no-store')])
            return [b'{"status":"alive","readiness":"not_assessed","synthetic_only":true}']
        if environ.get('HTTP_HOST') != self.hostname:
            start_response('400 Bad Request', [('Content-Type','application/json'),('Cache-Control','no-store')])
            return [b'{"error":{"code":"host_rejected"}}']
        for key in list(environ):
            if key == 'HTTP_FORWARDED' or key.startswith('HTTP_X_FORWARDED_') or key in ('HTTP_X_REAL_IP','HTTP_X_FORWARDED_SSL'):
                del environ[key]
        environ['wsgi.url_scheme'] = 'https'
        # A single conservative login limiter bucket; never trust a client-supplied IP.
        environ['REMOTE_ADDR'] = 'render-edge'
        return self.app(environ, start_response)


def load_render_app():
    if os.environ.get('RENDER') != 'true' or not os.environ.get('RENDER_SERVICE_ID'):
        raise ValueError('Render deployment environment required')
    config = json.loads(os.environ['CENTERWAY_MANAGED_CONFIG'])
    if config.get('demo') is not False or config.get('synthetic_only') is not True or config.get('session_store') != 'postgres':
        raise ValueError('Synthetic-only managed PostgreSQL configuration required')
    if not config.get('users'):
        raise ValueError('Provisioned users required')
    app = create_app(config)
    @app.after_request
    def synthetic_headers(response):
        response.headers['X-Centerway-Data'] = 'synthetic-only'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response
    return RenderEdge(app, os.environ['RENDER_EXTERNAL_HOSTNAME'])
