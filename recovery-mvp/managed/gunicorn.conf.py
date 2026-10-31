"""HTTP exclusively inside Render's TLS-terminating network boundary."""
import os
port = int(os.environ.get('PORT', '10000'))
if not 1 <= port <= 65535:
    raise ValueError('invalid port')
bind = f'0.0.0.0:{port}'
workers = 1
threads = 4
worker_class = 'gthread'
timeout = 60
graceful_timeout = 25
accesslog = None
errorlog = '-'
loglevel = 'warning'
secure_scheme_headers = {}
forwarded_allow_ips = ''
forwarder_headers = ''
proxy_protocol = False
