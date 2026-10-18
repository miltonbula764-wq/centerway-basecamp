"""Focused boundary tests with synthetic metadata, not remote Codespaces evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('demo_manager',Path(__file__).with_name('manage.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Boundaries(unittest.TestCase):
    def test_private_origin_requires_github_confirmation(self):
        with patch.dict(os.environ,{'CODESPACES':'true','CODESPACE_NAME':'synthetic-demo','GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN':'app.github.dev'}), patch.object(m.subprocess,'run') as call, patch.object(m.subprocess,'check_output',return_value='[{"sourcePort":8080,"visibility":"private"}]'):
            self.assertEqual(m.origin(),'https://synthetic-demo-8080.app.github.dev')
            self.assertIn('8080:private',call.call_args.args[0])
    def test_public_or_unconfirmed_port_fails_closed(self):
        with patch.dict(os.environ,{'CODESPACES':'true','CODESPACE_NAME':'synthetic-demo'}), patch.object(m.subprocess,'run'), patch.object(m.subprocess,'check_output',return_value='[{"sourcePort":8080,"visibility":"public"}]'):
            with self.assertRaises(RuntimeError):m.origin()
    def test_internal_forwarding_blocks_boot_even_when_private(self):
        with patch.dict(os.environ,{'CODESPACES':'true','CODESPACE_NAME':'synthetic-demo'}), patch.object(m.subprocess,'run'), patch.object(m.subprocess,'check_output',return_value='[{"sourcePort":8080,"visibility":"private"},{"sourcePort":5432,"visibility":"private"}]'):
            with self.assertRaises(RuntimeError):m.origin()
    def test_api_denial_never_falls_back_to_unprotected_origin(self):
        with patch.dict(os.environ,{'CODESPACES':'true','CODESPACE_NAME':'synthetic-demo'}), patch.object(m.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['gh'])):
            with self.assertRaises(subprocess.CalledProcessError):m.origin()
    def test_inherited_hosted_settings_removed(self):
        with patch.dict(os.environ,{'VITE_SUPABASE_URL':'https://synthetic-hosted.invalid','LOVABLE_DB_MIGRATION_URL':'synthetic-only','SUPABASE_SERVICE_ROLE_KEY':'synthetic-secret','GH_TOKEN':'synthetic-token'}):
            env=m.clean_env()
            for key in ('VITE_SUPABASE_URL','LOVABLE_DB_MIGRATION_URL','SUPABASE_SERVICE_ROLE_KEY','GH_TOKEN'):self.assertNotIn(key,env)
            self.assertEqual(env['PGHOST'],'127.0.0.1')
    def test_normal_machine_cannot_guess_remote_hostname(self):
        with patch.dict(os.environ,{'CODESPACES':'false','CW_DEMO_TLS_TEST':'0'}):
            with self.assertRaises(RuntimeError):m.origin()

if __name__=='__main__':unittest.main()
