"""Published routes and source ownership must survive the repository extraction."""
import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import app as documents


class RepositorySplitTests(unittest.TestCase):
    def test_every_historical_document_or_shared_route_is_still_mounted(self):
        paths = documents.app.openapi()['paths']
        expected = json.loads((Path(__file__).parent/'legacy-routes.json').read_text())
        for method, path in expected:
            with self.subTest(method=method, path=path):
                self.assertIn(method, paths[path])

    def test_content_and_shared_implementations_have_separate_owners(self):
        self.assertEqual(documents.upload.__module__, 'app')
        self.assertEqual(documents.check_admin.__module__, 'eduvize_admin.runtime')
        self.assertEqual(documents.microsoft_login.__class__.__module__, 'eduvize_admin.microsoft_login')
        root = Path(__file__).resolve().parents[1]
        for name in ['gallery.py','school_accounts.py','microsoft_login.py','configuration_profiles.py','update_plans.py']:
            self.assertFalse((root/name).exists(), name)

    def test_legacy_api_remains_protected_without_an_account(self):
        client = TestClient(documents.app)
        for path in ['/api/admin/gallery', '/api/admin/configuration-profiles', '/api/admin/documents']:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertIn(response.status_code, (401,503))
                self.assertNotIn('items', response.json())
