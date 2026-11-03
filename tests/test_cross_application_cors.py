"""School-app requests must reach authentication, rather than fail at CORS."""
import unittest
from fastapi.testclient import TestClient
import app


class CrossApplicationCors(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.path = '/api/admin/configuration-profiles/' + 'a'*32 + '/generated-links'

    def test_existing_application_origins_can_send_authenticated_profile_requests(self):
        origins = [
            'https://eduvize-prubeh-dne.onrender.com',
            'https://pborovicka72-dotcom.github.io',
            'https://eduvize-weather.onrender.com',
            'https://eduvize-aktuality.onrender.com',
            'https://eduvize-design-system-api.onrender.com',
            'https://eduvize-skolni-systemy.onrender.com',
            'http://127.0.0.1:8789',
            'https://eduvize-jidelnicek.onrender.com',
            'http://127.0.0.1:8790',
        ]
        for origin in origins:
            with self.subTest(origin=origin):
                response = self.client.options(self.path, headers={
                    'Origin': origin, 'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'authorization,content-type'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['access-control-allow-origin'], origin)
                self.assertIn('POST', response.headers['access-control-allow-methods'])
                # Successful preflight must not grant anonymous write access.
                response = self.client.post(self.path, headers={'Origin': origin}, json={})
                self.assertIn(response.status_code, (401,503))
                self.assertEqual(response.headers['access-control-allow-origin'], origin)

    def test_untrusted_origins_do_not_receive_cors_permission(self):
        for origin in ['https://other.example', 'https://eduvize-skolni-systemy.onrender.com.other.example', 'null']:
            with self.subTest(origin=origin):
                response = self.client.options(self.path, headers={
                    'Origin': origin, 'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'authorization,content-type'})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn('access-control-allow-origin', response.headers)
