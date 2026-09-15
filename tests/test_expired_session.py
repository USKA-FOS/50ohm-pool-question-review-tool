import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_campaign_backend import main


class ExpiredSessionTests(unittest.TestCase):
    def request(self, method="GET", token="private-test-token"):
        return SimpleNamespace(
            session={"token": token, "username": "test-user"} if token else {},
            cookies={main.LAST_CAMPAIGN_COOKIE: "default"},
            query_params={"reference_language": "de", "review_language": "fr"},
            method=method,
        )

    def error(self, status):
        response = main.requests.Response()
        response.status_code = status
        response.url = "https://api.github.com/repos/example/private"
        return main.requests.exceptions.HTTPError("simulated GitHub error", response=response)

    def test_detection_handles_falsey_401_response_and_ignores_other_errors(self):
        self.assertTrue(main.github_unauthorized(self.error(401)))
        for status in (403, 404, 500):
            self.assertFalse(main.github_unauthorized(self.error(status)))
        self.assertFalse(main.github_unauthorized(ValueError("invalid")))

    def test_campaign_401_clears_session_but_keeps_campaign(self):
        request = self.request()
        with patch.object(main, "fetch_path", side_effect=self.error(401)):
            response = main.index(request, "default")
        self.assertEqual(request.session, {})
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Login with GitHub", response.body)
        self.assertIn("50ohm_last_campaign=default", response.headers["set-cookie"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_403_and_404_do_not_log_out(self):
        for status in (403, 404):
            request = self.request()
            with patch.object(main, "fetch_path", side_effect=self.error(status)):
                response = main.index(request, "default")
            self.assertEqual(request.session["token"], "private-test-token")
            self.assertNotIn(b"session expired", response.body)

    def test_editor_401_clears_session(self):
        request = self.request()
        with patch.object(main, "fetch_path", side_effect=self.error(401)):
            response = main.edit_question(request, "default", "NF101")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(request.session, {})

    def test_save_401_preserves_fields_without_secrets_or_replay(self):
        request = self.request("POST")
        attack = "</script><script>alert(1)</script>"
        with (
            patch.object(main, "load_campaign", side_effect=self.error(401)),
            patch.object(main, "commit_campaign_files") as write,
        ):
            response = main.save_question(
                request, "default", "NF101", sha="test-sha", meta_sha="test-meta-sha",
                action="commit", question=attack, answer_a="answer",
                comment="unsaved comment", metadata_rationale=["reason one", "reason two"],
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(request.session, {})
        write.assert_not_called()
        body = response.body.decode()
        self.assertIn("&lt;/script&gt;", body)
        self.assertNotIn(attack, body)
        self.assertNotIn("private-test-token", body)
        self.assertNotIn("test-sha", body)
        encoded = body.split('id="expired-draft">')[1].split("</script>")[0]
        draft = json.loads(encoded)
        self.assertEqual(draft["fields"]["question"], attack)
        self.assertEqual(draft["fields"]["metadata_rationale"], ["reason one", "reason two"])
        self.assertEqual(draft["fields"]["comment"], "unsaved comment")
        self.assertEqual(draft["storage_key"], '50ohm-review-draft:["default","NF101","de","fr"]')
        self.assertNotIn("action", draft["fields"])

    def test_missing_session_on_save_preserves_inputs_instead_of_redirecting_post(self):
        response = main.save_question(
            self.request("POST", token=None), "default", "NF101",
            sha="test-sha", meta_sha="test-meta-sha", action="commit", question="unsaved text",
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"unsaved text", response.body)

    def test_oauth_user_401_clears_new_invalid_token(self):
        request = self.request()
        request.session.update(oauth_state="test-state", oauth_campaign_id="default")
        token_response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"access_token": "new-token"})
        def denied():
            raise self.error(401)
        user_response = SimpleNamespace(raise_for_status=denied)
        with patch.object(main, "github_request", side_effect=[token_response, user_response]):
            response = main.auth_callback("test-code", "test-state", request)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(request.session, {})

    def test_disabled_campaign_draft_never_moves_to_fallback_campaign(self):
        response = main.expired_session_response(self.request("POST"), "closed", "NF101", {"question": "original"})
        encoded = response.body.decode().split('id="expired-draft">')[1].split("</script>")[0]
        self.assertEqual(json.loads(encoded)["storage_key"], '50ohm-review-draft:["closed","NF101","de","fr"]')
        self.assertIn("50ohm_last_campaign=default", response.headers["set-cookie"])
