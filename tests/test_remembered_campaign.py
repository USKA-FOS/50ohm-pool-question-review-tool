import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_campaign_backend import main


class RememberedCampaignTests(unittest.TestCase):
    def setUp(self):
        self.configs = {
            "default": {"branch": "campaign/default", "label": "Default", "enabled": True},
            "chosen": {"branch": "campaign/chosen", "label": "Chosen", "enabled": True},
            "closed": {"branch": "campaign/closed", "label": "Closed", "enabled": False},
        }
        self.patches = [patch.object(main, "CAMPAIGNS", self.configs),
                        patch.object(main, "DEFAULT_CAMPAIGN", "default")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def request(self, remembered=None):
        cookies = {main.LAST_CAMPAIGN_COOKIE: remembered} if remembered else {}
        return SimpleNamespace(cookies=cookies, session={"token": "old-test-token"})

    def test_root_prefers_remembered_active_campaign(self):
        response = main.root(self.request("chosen"))
        self.assertEqual(response.headers["location"], "/campaign/chosen/")

    def test_unknown_disabled_or_malformed_cookie_falls_back(self):
        for value in ("missing", "closed", "https://evil.example/", "javascript:evil"):
            response = main.root(self.request(value))
            self.assertEqual(response.headers["location"], "/campaign/default/")
            self.assertIn("50ohm_last_campaign=default", response.headers["set-cookie"])

    def test_explicit_choice_overrides_cookie(self):
        request = self.request("chosen")
        response = main.login(request, "default")
        self.assertEqual(request.session["oauth_campaign_id"], "default")
        self.assertIn("50ohm_last_campaign=default", response.headers["set-cookie"])
        self.assertEqual(response.status_code, 307)

    def test_logout_preserves_preference_and_login_restores_it(self):
        request = self.request("chosen")
        response = main.logout(request)
        self.assertEqual(request.session, {})
        self.assertEqual(response.headers["location"], "/campaign/chosen/")
        self.assertIn("50ohm_last_campaign=chosen", response.headers["set-cookie"])
        main.login(request)
        self.assertEqual(request.session["oauth_campaign_id"], "chosen")

    def test_logout_with_stale_explicit_campaign_falls_back(self):
        response = main.logout(self.request("closed"), "closed")
        self.assertEqual(response.headers["location"], "/campaign/default/")

    def test_login_without_cookie_uses_configured_default(self):
        request = self.request()
        main.login(request)
        self.assertEqual(request.session["oauth_campaign_id"], "default")

    def test_explicit_disabled_login_is_rejected(self):
        self.assertEqual(main.login(self.request("chosen"), "closed").status_code, 404)

    def test_no_active_campaign_does_not_start_oauth(self):
        self.configs["default"]["enabled"] = False
        self.configs["chosen"]["enabled"] = False
        request = self.request("chosen")
        response = main.login(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("oauth_state", request.session)
        self.assertIn(b"No active review campaign", response.body)

    def test_cookie_is_persistent_secure_and_contains_only_campaign_id(self):
        with patch.dict(os.environ, {"SESSION_HTTPS_ONLY": "true"}):
            response = main.root(self.request("chosen"))
        cookie = response.headers["set-cookie"]
        for expected in ("50ohm_last_campaign=chosen", "HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=31536000"):
            self.assertIn(expected, cookie)
        self.assertNotIn("old-test-token", cookie)

    def callback(self, remembered="chosen", oauth_campaign="chosen"):
        request = self.request(remembered)
        request.session.update(oauth_state="test-state", oauth_campaign_id=oauth_campaign)
        responses = [
            SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"access_token": "test-new-token"}),
            SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"login": "test-user"}),
        ]
        with patch.object(main, "github_request", side_effect=responses):
            return main.auth_callback("test-code", "test-state", request)

    def test_callback_returns_to_oauth_selected_campaign(self):
        response = self.callback(remembered="default")
        self.assertEqual(response.headers["location"], "/campaign/chosen/")

    def test_callback_rechecks_campaign_closed_during_login(self):
        self.configs["chosen"]["enabled"] = False
        response = self.callback()
        self.assertEqual(response.headers["location"], "/campaign/default/")

    def test_invalid_oauth_state_still_rejected_before_github_call(self):
        request = self.request("chosen")
        request.session.update(oauth_state="valid", oauth_campaign_id="chosen")
        with patch.object(main, "github_request") as call:
            response = main.auth_callback("test-code", "invalid", request)
        self.assertEqual(response.status_code, 400)
        call.assert_not_called()

    def test_campaign_route_remembers_selection_even_on_fetch_error(self):
        request = self.request("default")
        request.url = SimpleNamespace(path="/campaign/chosen/edit/example")
        async def next_response(_):
            return main.HTMLResponse("upstream error", status_code=502)
        response = asyncio.run(main.remember_current_campaign(request, next_response))
        self.assertIn("50ohm_last_campaign=chosen", response.headers["set-cookie"])

    def test_disabled_route_never_replaces_cookie(self):
        request = self.request("chosen")
        request.url = SimpleNamespace(path="/campaign/closed/")
        async def next_response(_):
            return main.HTMLResponse("not found", status_code=404)
        response = asyncio.run(main.remember_current_campaign(request, next_response))
        self.assertNotIn("set-cookie", response.headers)
