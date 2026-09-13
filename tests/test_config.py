import os
import unittest
from unittest.mock import patch

from config import load_settings


class ConfigTests(unittest.TestCase):
    def test_mini_app_config(self):
        env = {'TELEGRAM_TOKEN': 'x', 'OPENAI_API_KEY': 'y', 'OWNER_USER_ID': '42'}
        for url in ('http://example.com', 'https://user:pass@example.com', 'https://example.com/#secret'):
            with patch.dict(os.environ, {**env, 'MINI_APP_URL': url}, clear=True):
                with self.assertRaises(RuntimeError):
                    load_settings(None)
        with patch.dict(os.environ, {**env, 'MINI_APP_URL': 'https://example.com', 'MINI_APP_PORT': '8766'}, clear=True):
            self.assertEqual(load_settings(None).mini_app_port, 8766)
        with patch.dict(os.environ, {**env, 'MINI_APP_PORT': '0'}, clear=True):
            with self.assertRaises(RuntimeError):
                load_settings(None)
    def test_additional_accounts_and_invalid_allowlist(self):
        env = {'TELEGRAM_TOKEN': 'x', 'OPENAI_API_KEY': 'y', 'OWNER_USER_ID': '42'}
        with patch.dict(os.environ, {**env, 'ALLOWED_USER_IDS': '7, 8'}, clear=True):
            self.assertEqual(load_settings(None).allowed_user_ids, frozenset({7, 8}))
        for bad in ('7, nope', '0', '-2', '7,'):
            with patch.dict(os.environ, {**env, 'ALLOWED_USER_IDS': bad}, clear=True):
                with self.assertRaises(RuntimeError):
                    load_settings(None)
    def test_required_and_defaults(self):
        env = {"TELEGRAM_TOKEN": "telegram", "OPENAI_API_KEY": "openai", "OWNER_USER_ID": "42"}
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings(None)
        self.assertEqual(settings.owner_user_id, 42)
        self.assertEqual(settings.nutrition_model, "gpt-6-astra")
        self.assertEqual(settings.transcription_model, "whisper-1")
        self.assertEqual(settings.response_language, "English")

    def test_response_language_override(self):
        env = {"TELEGRAM_TOKEN": "telegram", "OPENAI_API_KEY": "openai", "OWNER_USER_ID": "42",
               "RESPONSE_LANGUAGE": "Italian"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(load_settings(None).response_language, "Italian")

    def test_missing_owner_fails_closed(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "x", "OPENAI_API_KEY": "y"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OWNER_USER_ID"):
                load_settings(None)

    def test_invalid_owner_fails(self):
        env = {"TELEGRAM_TOKEN": "x", "OPENAI_API_KEY": "y", "OWNER_USER_ID": "no"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "integer"):
                load_settings(None)
