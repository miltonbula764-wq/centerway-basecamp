"""Keep L01 unchanged: HTTPS is a real TLS socket, never an assertion in a header."""
import os
import re
import ssl

bind = os.environ.get('CENTERWAY_UPSTREAM_ADDR', '127.0.0.1:8444')
match = re.fullmatch(r'127\.0\.0\.1:([0-9]{1,5})', bind)
if not match or not 1 <= int(match.group(1)) <= 65535:
    raise ValueError('The upstream must bind to IPv4 loopback only')
certfile = os.environ['CENTERWAY_TLS_CERT']
keyfile = os.environ['CENTERWAY_TLS_KEY']
workers = 1
threads = 4
worker_class = 'gthread'
timeout = 30
accesslog = None
errorlog = '-'
loglevel = 'warning'
secure_scheme_headers = {}
forwarded_allow_ips = ''
forwarder_headers = ''
proxy_protocol = False

def ssl_context(conf, default_ssl_context_factory):
    context = default_ssl_context_factory()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
