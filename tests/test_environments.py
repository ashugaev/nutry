import unittest
from pathlib import Path
from unittest.mock import patch
from services.environments import dev_values


class EnvironmentTests(unittest.TestCase):
    def test_separate_environment_and_fail_closed_aliases(self):
        production={'TELEGRAM_TOKEN':'123:prod','NOTION_DATABASE_ID':'aa-bb','DATABASE_PATH':'.data/prod.db',
                    'MINI_APP_URL':'https://example.test:8443','MINI_APP_PORT':'8765'}
        dev={'TELEGRAM_TOKEN':'456:dev','NOTION_DATABASE_ID':'cc-dd','DATABASE_PATH':'.data/dev.db',
             'MINI_APP_URL':'https://example.test:10000','MINI_APP_PORT':'8766'}
        with patch('services.environments.dotenv_values',side_effect=[production,dev]):
            self.assertEqual(dev_values(Path('/project')),dev)
        for change in ({'TELEGRAM_TOKEN':'123:rotated'}, {'TELEGRAM_TOKEN':' 123:prod '},
                       {'NOTION_DATABASE_ID':'AABB'}, {'DATABASE_PATH':'.data/../.data/prod.db'},
                       {'MINI_APP_PORT':'08765'}, {'MINI_APP_URL':production['MINI_APP_URL']},
                       {'TELEGRAM_TOKEN':''}, {'NOTION_DATABASE_ID':''}):
            with self.subTest(change=change), patch('services.environments.dotenv_values',side_effect=[production,{**dev,**change}]):
                with self.assertRaises(RuntimeError): dev_values(Path('/project'))
