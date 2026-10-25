"""Verified TLS mock endpoint only; no real AI model or external inference is used."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from centerway.ai_adapter import HTTPSChatAdapter,ProviderError,configured_adapter
from centerway.integrations import canonical


class AITransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.cert=cls.root/'cert.pem';cls.key=cls.root/'tls.key'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(cls.key),'-out',str(cls.cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],check=True,capture_output=True)
        cls.cert.chmod(0o600)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    @contextmanager
    def endpoint(self,mode='valid'):
        state={'requests':[],'mode':mode};key='test-only-credential-not-a-real-api-key'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                state['requests'].append({'path':self.path,'authorization':self.headers.get('Authorization'),'body':body})
                if state['mode']=='timeout': time.sleep(1.3)
                envelope={'id':'mock-response','model':'mock-model-not-real','choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'{"mock":true}'}}]}
                if state['mode']=='tool': envelope['choices'][0]['message']['tool_calls']=[{'name':'unauthorized'}]
                if state['mode']=='truncated': envelope['choices'][0]['finish_reason']='length'
                if state['mode'] in ('secret','encoded-secret'): envelope['choices'][0]['message']['content']=key
                if state['mode']=='missing-model': envelope.pop('model')
                payload=canonical(envelope).encode()
                if state['mode']=='encoded-secret': payload=payload.replace(key.encode(),''.join('\\u%04x'%ord(c) for c in key).encode())
                if state['mode']=='oversize': payload=b'x'*65537
                self.send_response(302 if state['mode']=='redirect' else 500 if state['mode']=='error' else 200)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)))
                if state['mode']=='redirect': self.send_header('Location','https://unapproved.example.invalid/steal')
                self.end_headers()
                try: self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError,ssl.SSLError): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(self.cert,self.key)
        server.socket=tls.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);secret=root/'provider.key';secret.write_text(key);secret.chmod(0o600)
            # Copy the public test CA into this private configuration directory.
            ca=root/'ca.pem';ca.write_bytes(self.cert.read_bytes());ca.chmod(0o600)
            config={'protocol':'https-chat-completions-v1','endpoint':f'https://127.0.0.1:{server.server_port}/v1/chat/completions','model':'mock-requested-model',
                    'api_key_file':str(secret),'ca_file':str(ca),'allowed_tenants':['saas-a'],'allowed_classifications':['synthetic'],
                    'allow_production_inference':False,'max_output_tokens':100,'timeout_seconds':1}
            path=root/'provider.json';path.write_text(json.dumps(config));path.chmod(0o600)
            try: yield state,config,path,key
            finally: server.shutdown();server.server_close();thread.join()

    def context(self): return {'lineage':{'tenant':'saas-a'},'classification':'synthetic','runtime_mode':'sandbox','response_contract':{},'context_hash':'0'*64}

    def test_authorized_generic_protocol_uses_verified_https_and_records_reported_model(self):
        with self.endpoint() as (state,config,path,key):
            adapter=HTTPSChatAdapter(path);completion=adapter.generate(self.context())
            self.assertEqual('mock-model-not-real',completion.reported_model);self.assertEqual('mock-response',completion.response_id)
            self.assertEqual('{"mock":true}',completion.content)
            self.assertEqual(1,len(state['requests']));request=state['requests'][0]
            self.assertEqual('Bearer '+key,request['authorization'])
            self.assertEqual('mock-requested-model',request['body']['model'])
            self.assertEqual({'type':'json_object'},request['body']['response_format'])
            self.assertEqual(['system','user'],[m['role'] for m in request['body']['messages']])
            self.assertNotIn(key,canonical(adapter.descriptor()));self.assertNotIn('api_key_file',adapter.descriptor())
            self.assertTrue(adapter._tls.check_hostname);self.assertEqual(ssl.CERT_REQUIRED,adapter._tls.verify_mode)

    def test_redirect_errors_tools_truncation_oversize_and_secret_echo_fail_closed(self):
        for mode,code in (('redirect','provider_redirect_refused'),('error','provider_http_failure'),('tool','provider_incomplete_or_refused'),
                          ('truncated','provider_incomplete_or_refused'),('oversize','provider_response_too_large'),
                          ('secret','provider_secret_echo_refused'),('encoded-secret','provider_secret_echo_refused'),('missing-model','provider_invalid_envelope'),('timeout','provider_transport_failure')):
            with self.subTest(mode=mode),self.endpoint(mode) as (state,config,path,key):
                with self.assertRaises(ProviderError) as error: HTTPSChatAdapter(path).generate(self.context())
                self.assertEqual(code,error.exception.code);self.assertNotIn(key,str(error.exception));self.assertEqual(1,len(state['requests']))

    def test_no_insecure_tls_fallback_or_unauthorized_data_transfer(self):
        with self.endpoint() as (state,config,path,key):
            adapter=HTTPSChatAdapter(path)
            for change in ({'lineage':{'tenant':'foreign'}},{'classification':'declared'},{'runtime_mode':'production'}):
                context={**self.context(),**change}
                with self.assertRaises(ProviderError) as error: adapter.generate(context)
                self.assertEqual('provider_data_not_authorized',error.exception.code)
            self.assertEqual([],state['requests'])
            with self.assertRaises(ProviderError) as error: adapter.generate({**self.context(),'accidental_secret':key})
            self.assertEqual('context_contains_provider_secret',error.exception.code);self.assertEqual([],state['requests'])
            config['ca_file']=None;path.write_text(json.dumps(config))
            with self.assertRaises(ProviderError) as error: HTTPSChatAdapter(path).generate(self.context())
            self.assertEqual('provider_transport_failure',error.exception.code);self.assertEqual([],state['requests'])

    def test_public_files_invalid_endpoints_and_missing_secrets_never_create_a_live_adapter(self):
        with self.endpoint() as (state,config,path,key):
            for endpoint in ('http://provider.example.invalid/v1/chat/completions','https://u:p@provider.example.invalid/v1','https://provider.example.invalid/v1?key=secret'):
                bad={**config,'endpoint':endpoint};path.write_text(json.dumps(bad))
                adapter=configured_adapter(path);self.assertEqual('unavailable',adapter.inference_kind)
            path.write_text(json.dumps(config));path.chmod(0o644)
            self.assertEqual('unavailable',configured_adapter(path).inference_kind)
            path.chmod(0o600);Path(config['api_key_file']).unlink()
            self.assertEqual('unavailable',configured_adapter(path).inference_kind);self.assertEqual([],state['requests'])
