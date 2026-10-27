"""Public distribution defaults must not silently grant access or spend money."""
import json
from pathlib import Path
import unittest

from astrbot_plugin_family_memory.security import IdentityPolicy, Rejected

ROOT = Path(__file__).resolve().parents[1]


class PublicDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'config.template.json').read_text(encoding='utf-8'))

    def test_no_model_calls_or_sharing_enabled(self):
        for field in ['enabled', 'allow_llm_extraction', 'botchat_guard_enabled', 'elder_private_mutual_read']:
            self.assertIs(self.config[field], False)
        self.assertEqual(self.config['max_summary_calls_per_day'], 0)
        self.assertEqual(self.config['summary_provider_id'], '')

    def test_no_trusted_identity_prepopulated(self):
        self.assertEqual(self.config['xiaoman_self_id'], '')
        self.assertEqual(self.config['owner_qq_ids'], [])
        self.assertEqual(self.config['elder_owner_openids'], [])
        self.assertEqual(self.config['botchat_peer_umos'], [])
        for field in ['sister_binding', 'elder_peer_binding']:
            self.assertIs(self.config[field]['approved'], False)
            self.assertEqual(self.config[field]['evidence_ref'], '')
        with self.assertRaises(Rejected):
            IdentityPolicy(b'synthetic-public-key', self.config).resolve('default', 'fixture-bot', 'fixture-user')

    def test_schema_and_template_defaults_match(self):
        schema = json.loads((ROOT / '_conf_schema.json').read_text(encoding='utf-8'))
        def unpack(items):
            return {k: unpack(v['items']) if v['type'] == 'object' else v['default'] for k, v in items.items()}
        self.assertEqual(self.config, unpack(schema))

    def test_public_version_and_repository(self):
        metadata = (ROOT / 'metadata.yaml').read_text(encoding='utf-8')
        self.assertIn('version: 0.1.8', metadata)
        self.assertIn('https://github.com/terringzhang/astrbot_plugin_family_memory', metadata)
