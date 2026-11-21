import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from starlette.requests import Request

from test_campaign_backend import main


class UrlPrefixTests(unittest.TestCase):
    def setUp(self):
        self.prefix = '/isq/qrt'
        self.prefix_patch = patch.object(main, 'URL_PREFIX', self.prefix)
        self.prefix_patch.start()
        self.addCleanup(self.prefix_patch.stop)
        self.original_template_prefix = main.templates.env.globals['url_prefix']
        main.templates.env.globals['url_prefix'] = self.prefix
        self.addCleanup(main.templates.env.globals.__setitem__, 'url_prefix', self.original_template_prefix)

    def request(self):
        return Request({
            'type': 'http', 'method': 'GET', 'scheme': 'https',
            'server': ('50ohm.uska.ch', 443), 'client': ('127.0.0.1', 1234),
            'path': '/campaign/default/', 'root_path': self.prefix,
            'headers': [], 'query_string': b'', 'session': {},
        })

    def test_redirects_oauth_and_cookies_remain_under_prefix(self):
        request = self.request()
        self.assertEqual(main.root(request).headers['location'], '/isq/qrt/campaign/default/')
        self.assertEqual(main.edit_question(request, 'default', 'NF101').headers['location'],
                         '/isq/qrt/login?campaign_id=default')
        with patch.object(main, 'CALLBACK_URL', 'https://50ohm.uska.ch/isq/qrt/auth/callback'):
            login = main.login(request, 'default')
        query = parse_qs(urlsplit(login.headers['location']).query)
        self.assertEqual(query['redirect_uri'], ['https://50ohm.uska.ch/isq/qrt/auth/callback'])
        self.assertIn('Path=/isq/qrt', login.headers['set-cookie'])
        response = main.HTMLResponse('ok')
        main.remember_review_preferences(response, 'de', 'fr')
        self.assertIn('Path=/isq/qrt', response.headers['set-cookie'])

    def test_rendered_campaign_page_has_prefixed_internal_links(self):
        response = main.index(self.request(), 'default')
        self.assertEqual(response.status_code, 200)
        html = response.body.decode()
        for attribute in re.findall(r'(?:href|src|action)="(/[^"]*)"', html):
            self.assertTrue(attribute.startswith('/isq/qrt/'), attribute)
        self.assertIn('href="/isq/qrt/login?campaign_id=default"', html)
        self.assertIn('href="/isq/qrt/static/style.css?', html)

    def test_expired_session_link_and_script_are_prefixed(self):
        request = SimpleNamespace(
            session={'token': 'test'}, cookies={}, query_params={}, method='POST',
        )
        response = main.expired_session_response(request, 'default', 'NF101', {'question': 'test'})
        html = response.body.decode()
        self.assertIn('href="/isq/qrt/login?campaign_id=default"', html)
        self.assertIn('src="/isq/qrt/static/review-draft.js"', html)
