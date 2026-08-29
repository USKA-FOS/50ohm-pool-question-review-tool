import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


os.environ["GITHUB_CLIENT_ID"] = "test-client"
os.environ["GITHUB_CLIENT_SECRET"] = "test-secret"
os.environ["GITHUB_OWNER"] = "isqsoft"
os.environ["GITHUB_REPO"] = "50ohm-question-review-campaigns"
os.environ["CAMPAIGN_BRANCH"] = "campaign/test"
os.environ["GITHUB_CALLBACK_URL"] = "http://localhost:8080/auth/callback"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["SESSION_HTTPS_ONLY"] = "false"

import main


class CampaignBackendTests(unittest.TestCase):
    def test_campaign_configuration_supports_multiple_named_branches(self) -> None:
        configs = main.load_campaign_configs(
            '{"receiver":{"branch":"campaign/receiver","label":"Receiver review"},'
            '"antennas":"campaign/antennas"}',
            None,
            "receiver",
        )

        self.assertEqual(configs["receiver"]["branch"], "campaign/receiver")
        self.assertEqual(configs["receiver"]["label"], "Receiver review")
        self.assertEqual(configs["antennas"]["branch"], "campaign/antennas")
        with self.assertRaisesRegex(RuntimeError, "DEFAULT_CAMPAIGN"):
            main.load_campaign_configs('{"receiver":"campaign/receiver"}', None, "missing")

    def test_campaign_snapshots_are_isolated_by_campaign(self) -> None:
        configs = {
            "first": {"branch": "campaign/first", "label": "First"},
            "second": {"branch": "campaign/second", "label": "Second"},
        }
        snapshots = {
            "first-head": {"campaign.meta.json": {"sha": "first", "json": {}}},
            "first-export": {"campaign.meta.json": {"sha": "first-export", "json": {}}},
            "second-head": {"campaign.meta.json": {"sha": "second", "json": {}}},
            "second-export": {"campaign.meta.json": {"sha": "second-export", "json": {}}},
        }
        with (
            patch.object(main, "CAMPAIGNS", configs),
            patch.object(main, "CAMPAIGN_SNAPSHOTS", {}),
            patch.object(
                main,
                "campaign_branch_head",
                side_effect=lambda campaign_id, token: f"{campaign_id}-head",
            ),
            patch.object(
                main,
                "oldest_campaign_commit_for_path",
                side_effect=lambda campaign_id, path, token: f"{campaign_id}-export",
            ),
            patch.object(
                main,
                "download_campaign_snapshot",
                side_effect=lambda ref, token: snapshots[ref],
            ),
        ):
            first = main.ensure_campaign_snapshot("first", "token")
            second = main.ensure_campaign_snapshot("second", "token")

        self.assertEqual(first["head_sha"], "first-head")
        self.assertEqual(second["head_sha"], "second-head")
        self.assertIsNot(first, second)

    def test_campaign_urls_include_the_campaign_identifier(self) -> None:
        self.assertEqual(main.campaign_url("receiver"), "/campaign/receiver/")
        self.assertEqual(
            main.edit_url("receiver", "NF101", "de", "fr"),
            "/campaign/receiver/edit/NF101?reference_language=de&review_language=fr",
        )

    def test_login_remembers_the_requested_campaign_for_oauth_callback(self) -> None:
        request = SimpleNamespace(session={})

        response = main.login(request, "default")

        self.assertEqual(response.status_code, 307)
        self.assertEqual(request.session["oauth_campaign_id"], "default")
        self.assertTrue(request.session["oauth_state"])
        self.assertIn("github.com/login/oauth/authorize", response.headers["location"])

    def test_login_rejects_an_unconfigured_campaign(self) -> None:
        response = main.login(SimpleNamespace(session={}), "missing")

        self.assertEqual(response.status_code, 404)

    def test_original_question_uses_export_snapshot(self) -> None:
        manifest = {
            "question_ids": ["q_111111111111"],
        }
        expected = {"sha": "original-sha", "json": {"question": "Original?"}}

        snapshot = {
            "original_files": {
                "pool/questions/q_111111111111/question.fr.json": expected,
            }
        }
        with patch.object(main, "ensure_campaign_snapshot", return_value=snapshot) as ensure:
            result = main.fetch_original_question(
                "default", manifest, "q_111111111111", "fr", "token"
            )

        self.assertIs(result, expected)
        ensure.assert_called_once_with("default", "token")

    def test_campaign_snapshot_is_loaded_only_once(self) -> None:
        current = {"campaign.meta.json": {"sha": "meta", "json": {}}}
        original = {"campaign.meta.json": {"sha": "original-meta", "json": {}}}
        with (
            patch.object(main, "CAMPAIGN_SNAPSHOTS", {}),
            patch.object(main, "campaign_branch_head", return_value="head") as branch_head,
            patch.object(main, "oldest_campaign_commit_for_path", return_value="export") as oldest,
            patch.object(main, "download_campaign_snapshot", side_effect=[current, original]) as download,
        ):
            first = main.ensure_campaign_snapshot("default", "token")
            second = main.ensure_campaign_snapshot("default", "token")

        self.assertIs(first, second)
        self.assertEqual(first["head_sha"], "head")
        branch_head.assert_called_once_with("default", "token")
        oldest.assert_called_once_with("default", "campaign.meta.json", "token")
        self.assertEqual(download.call_count, 2)

    def test_expired_snapshot_refreshes_only_current_archive_when_head_changed(self) -> None:
        old_snapshot = {
            "head_sha": "old-head",
            "export_sha": "export",
            "current_files": {"current": "old"},
            "original_files": {"original": "fixed"},
            "checked_at": 0.0,
        }
        refreshed = {"campaign.meta.json": {"sha": "meta", "json": {}}}
        with (
            patch.object(main, "CAMPAIGN_SNAPSHOTS", {"default": old_snapshot}),
            patch.object(main, "CAMPAIGN_REFRESH_SECONDS", 30.0),
            patch.object(main.time, "monotonic", return_value=60.0),
            patch.object(main, "campaign_branch_head", return_value="new-head"),
            patch.object(main, "download_campaign_snapshot", return_value=refreshed) as download,
            patch.object(main, "oldest_campaign_commit_for_path") as oldest,
        ):
            result = main.ensure_campaign_snapshot("default", "token")

        self.assertEqual(result["head_sha"], "new-head")
        self.assertIs(result["current_files"], refreshed)
        self.assertEqual(result["original_files"], {"original": "fixed"})
        download.assert_called_once_with("new-head", "token")
        oldest.assert_not_called()

    def test_oldest_campaign_commit_follows_last_page(self) -> None:
        first_page = SimpleNamespace(
            links={"last": {"url": "https://api.github.com/example?page=4"}},
            raise_for_status=lambda: None,
            json=lambda: [{"sha": "newest"}],
        )
        last_page = SimpleNamespace(
            links={},
            raise_for_status=lambda: None,
            json=lambda: [{"sha": "oldest"}],
        )

        with patch.object(main, "github_request", side_effect=[first_page, last_page]) as request:
            result = main.oldest_campaign_commit_for_path(
                "default", "pool/questions/q/question.fr.json", "token"
            )

        self.assertEqual(result, "oldest")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].args[1], "https://api.github.com/example?page=4")

    def test_github_profiler_records_duration_without_payload(self) -> None:
        response = SimpleNamespace(
            status_code=200,
            headers={
                "x-github-request-id": "github-request",
                "x-ratelimit-remaining": "4999",
            },
        )
        events = []
        events_token = main.PROFILE_EVENTS.set(events)
        request_token = main.PROFILE_REQUEST_ID.set("request-1")
        try:
            with (
                patch.object(main, "GITHUB_PROFILE", True),
                patch.object(main.requests, "request", return_value=response) as request_call,
                patch.object(main.time, "perf_counter", side_effect=[10.0, 10.125]),
                patch.object(main.LOGGER, "info") as log_info,
            ):
                result = main.github_request(
                    "GET",
                    "https://api.github.com/example",
                    operation="contents.read",
                    resource="campaign.meta.json",
                    headers={"Authorization": "Bearer secret"},
                )
        finally:
            main.PROFILE_REQUEST_ID.reset(request_token)
            main.PROFILE_EVENTS.reset(events_token)

        self.assertIs(result, response)
        self.assertEqual(events[0]["operation"], "contents.read")
        self.assertEqual(events[0]["resource"], "campaign.meta.json")
        self.assertEqual(events[0]["duration_ms"], 125.0)
        self.assertNotIn("secret", str(log_info.call_args))
        request_call.assert_called_once()

    def test_atomic_commit_updates_multiple_cached_files(self) -> None:
        snapshot = {
            "head_sha": "old-head",
            "current_files": {},
            "original_files": {},
        }
        response = SimpleNamespace(
            status_code=200,
            headers={},
            raise_for_status=lambda: None,
            json=lambda: {
                "data": {
                    "createCommitOnBranch": {
                        "commit": {"oid": "new-head"},
                    }
                }
            },
        )
        changes = {
            "question.json": {"question": "Corrected?"},
            "question.meta.json": {"review": {"fr": "approved"}},
        }

        with (
            patch.object(main, "CAMPAIGN_SNAPSHOTS", {"default": snapshot}),
            patch.object(main, "github_request", return_value=response) as request,
        ):
            result = main.commit_campaign_files(
                "default", changes, "Commit review", "old-head", "token"
            )

        self.assertEqual(result, "new-head")
        self.assertEqual(snapshot["head_sha"], "new-head")
        self.assertEqual(snapshot["current_files"]["question.json"]["json"], changes["question.json"])
        graphql_input = request.call_args.kwargs["json"]["variables"]["input"]
        self.assertEqual(graphql_input["expectedHeadOid"], "old-head")
        self.assertEqual(len(graphql_input["fileChanges"]["additions"]), 2)

    def test_canonical_question_is_adapted_without_changing_null(self) -> None:
        payload = {
            "question": "Question?",
            "answer_a": "A",
            "answer_b": None,
            "answer_c": "C",
            "answer_d": "D",
            "picture_question_url": 101,
            "picture_answer_a_url": None,
            "picture_answer_b_url": 102,
            "picture_answer_c_url": None,
            "picture_answer_d_url": None,
        }

        adapted = main.canonical_to_legacy_question(payload)

        self.assertIsNone(adapted["answer_b"])
        self.assertEqual(adapted["picture_question"], 101)
        self.assertEqual(adapted["picture_b"], 102)

    def test_status_change_preserves_other_languages(self) -> None:
        meta = {
            "id": "q_111111111111",
            "review": {"de": "approved", "fr": "to_be_reviewed", "it": "rejected"},
            "external_refs": [],
        }

        reopened = main.meta_with_status(meta, "q_111111111111", "fr", "to_be_reviewed")
        approved = main.meta_with_status(reopened, "q_111111111111", "fr", "approved")

        self.assertEqual(approved["review"]["fr"], "approved")
        self.assertEqual(approved["review"]["it"], "rejected")
        self.assertEqual(meta["review"]["fr"], "to_be_reviewed")

        self.assertEqual(reopened["review"]["fr"], "to_be_reviewed")

    def test_content_edits_preserve_metadata_media_and_null(self) -> None:
        content = {
            "question_id": "q_111111111111",
            "language": "it",
            "question": "Domanda?",
            "answer_a": "A",
            "answer_b": None,
            "answer_c": "C",
            "answer_d": "D",
            "picture_question_url": 101,
        }

        updated = main.content_with_edits(
            content,
            "q_111111111111",
            "it",
            {
                "question": "Domanda corretta?",
                "answer_a": "A corretta",
                "answer_b": None,
                "answer_c": "C",
                "answer_d": "D",
            },
        )

        self.assertEqual(updated["question"], "Domanda corretta?")
        self.assertIsNone(updated["answer_b"])
        self.assertEqual(updated["picture_question_url"], 101)
        self.assertEqual(content["question"], "Domanda?")

    def test_media_urls_use_the_immutable_campaign_manifest(self) -> None:
        manifest = {
            "schema_version": 1,
            "repository": "USKA-FOS/50ohm-contents-ch",
            "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "items": {
                "202": {
                    "kind": "drawing",
                    "variants": {
                        "fr": {
                            "path": "canonical/drawings/dr_example/202.fr.svg",
                            "source_language": "fr",
                            "media_type": "image/svg+xml",
                        }
                    },
                }
            },
        }

        url = main.media_url(manifest, 202, "fr")

        self.assertEqual(
            url,
            "https://raw.githubusercontent.com/USKA-FOS/50ohm-contents-ch/"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/"
            "canonical/drawings/dr_example/202.fr.svg",
        )
        self.assertIsNone(main.media_url(manifest, None, "fr"))
        with self.assertRaisesRegex(ValueError, "no it variant"):
            main.media_url(manifest, 202, "it")

    def test_campaign_load_builds_toc_and_marks_approved_questions(self) -> None:
        manifest = {
            "campaign_branch": "campaign/test",
            "languages": ["de", "fr"],
            "editable_languages": ["fr"],
        }
        navigation = {
            "sections": [
                {
                    "title": "Root",
                    "sections": [
                        {
                            "title": "Section",
                            "sections": [
                                {
                                    "title": "Empfänger",
                                    "questions": [
                                        {"number": "NF101"},
                                        {"number": "NF102"},
                                    ],
                                }
                            ],
                        },
                        {
                            "title": "Other section",
                            "sections": [
                                {
                                    "title": "Sinusförmige Signale",
                                    "questions": [
                                        {"number": "NF201"},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        index = {
            "items": [
                {
                    "question_id": "q_111111111111",
                    "internal_code": "NF101",
                    "review": {"de": "approved", "fr": "to_be_reviewed"},
                },
                {
                    "question_id": "q_222222222222",
                    "internal_code": "NF102",
                    "review": {"de": "approved", "fr": "to_be_reviewed"},
                },
                {
                    "question_id": "q_333333333333",
                    "internal_code": "NF201",
                    "review": {"de": "approved", "fr": "to_be_reviewed"},
                },
            ]
        }
        payloads = {
            "campaign.meta.json": manifest,
            "derived/question_pool_ch-de.json": navigation,
            "derived/navigation.index.json": index,
            "pool/questions/q_111111111111/question.meta.json": {
                "id": "q_111111111111",
                "review": {"de": "approved", "fr": "approved"},
            },
            "pool/questions/q_222222222222/question.meta.json": {
                "id": "q_222222222222",
                "review": {"de": "approved", "fr": "to_be_reviewed"},
            },
            "pool/questions/q_333333333333/question.meta.json": {
                "id": "q_333333333333",
                "review": {"de": "approved", "fr": "to_be_reviewed"},
            },
        }

        with patch.object(
            main,
            "fetch_path",
            side_effect=lambda campaign_id, ref, path, token: {"sha": path, "json": payloads[path]},
        ):
            loaded_manifest, campaign_toc, questions, reference_language, review_language = main.load_campaign(
                "default", "token"
            )

        self.assertEqual(loaded_manifest, manifest)
        self.assertEqual(questions["NF102"]["question_id"], "q_222222222222")
        self.assertEqual(reference_language, "de")
        self.assertEqual(review_language, "fr")
        self.assertTrue(campaign_toc.question_map["NF101"].reviewed)
        self.assertFalse(campaign_toc.question_map["NF102"].reviewed)
        self.assertEqual(campaign_toc.next_q_in_subsection("NF101"), "NF102")
        self.assertEqual(campaign_toc.next_q_in_section("NF101"), "NF201")
        self.assertEqual(campaign_toc.prev_q_in_section("NF201"), "NF101")
        self.assertIsNone(campaign_toc.prev_q_in_section("NF101"))
        self.assertIsNone(campaign_toc.next_q_in_section("NF201"))

    def test_language_selection_allows_same_language_review(self) -> None:
        manifest = {
            "languages": ["de", "fr", "it"],
            "editable_languages": ["de", "fr", "it"],
        }

        self.assertEqual(main.select_languages(manifest), ("de", "fr"))
        self.assertEqual(main.select_languages(manifest, "fr", "it"), ("fr", "it"))
        self.assertEqual(main.select_languages(manifest, "de", "de"), ("de", "de"))
        self.assertEqual(main.select_languages(manifest, "fr", "fr"), ("fr", "fr"))
        self.assertEqual(main.select_languages(manifest, "it", "it"), ("it", "it"))
        monolingual_manifest = {
            "languages": ["de"],
            "editable_languages": ["de"],
        }
        self.assertEqual(main.select_languages(monolingual_manifest), ("de", "de"))
        self.assertEqual(main.select_languages(monolingual_manifest, "de", "de"), ("de", "de"))
        restricted_manifest = {
            "languages": ["de", "fr", "it"],
            "editable_languages": ["fr", "it"],
        }
        with self.assertRaisesRegex(ValueError, "not editable"):
            main.select_languages(restricted_manifest, "fr", "de")

    def test_remembered_languages_are_validated_and_query_parameters_win(self) -> None:
        manifest = {
            "languages": ["de", "fr", "it"],
            "editable_languages": ["fr", "it"],
        }
        remembered = SimpleNamespace(
            query_params={},
            cookies={
                main.REFERENCE_LANGUAGE_COOKIE: "it",
                main.REVIEW_LANGUAGE_COOKIE: "fr",
            },
        )
        self.assertEqual(main.requested_languages(remembered, manifest), ("it", "fr"))

        explicit = SimpleNamespace(
            query_params={"reference_language": "de", "review_language": "it"},
            cookies={
                main.REFERENCE_LANGUAGE_COOKIE: "fr",
                main.REVIEW_LANGUAGE_COOKIE: "fr",
            },
        )
        self.assertEqual(main.requested_languages(explicit, manifest), ("de", "it"))

        obsolete = SimpleNamespace(
            query_params={},
            cookies={
                main.REFERENCE_LANGUAGE_COOKIE: "en",
                main.REVIEW_LANGUAGE_COOKIE: "de",
            },
        )
        self.assertEqual(main.requested_languages(obsolete, manifest), (None, None))

    def test_review_preferences_are_written_as_persistent_cookies(self) -> None:
        calls = []
        response = SimpleNamespace(
            set_cookie=lambda key, value, **options: calls.append((key, value, options))
        )

        main.remember_review_preferences(response, "de", "fr", "NF101")

        self.assertEqual(
            [(key, value) for key, value, _ in calls],
            [
                (main.REFERENCE_LANGUAGE_COOKIE, "de"),
                (main.REVIEW_LANGUAGE_COOKIE, "fr"),
                (main.LAST_QUESTION_COOKIE, "NF101"),
            ],
        )
        for _, _, options in calls:
            self.assertEqual(options["max_age"], 365 * 24 * 60 * 60)
            self.assertTrue(options["httponly"])
            self.assertEqual(options["samesite"], "lax")
            self.assertFalse(options["secure"])

    def test_templates_render_and_preserve_dynamic_language_query(self) -> None:
        request = SimpleNamespace(session={"token": "test-token"})
        index_html = main.templates.get_template("index.html").render(
            request=request,
            logged_in=True,
            toc=[],
            rate_limit_json=None,
            languages=["de", "fr", "it"],
            editable_languages=["de", "fr", "it"],
            reference_language="de",
            review_language="fr",
            remembered_question="NF101",
            language_labels=main.LANGUAGE_LABELS,
            campaign_id="default",
            campaign_label="Test campaign",
        )
        self.assertIn('name="reference_language"', index_html)
        self.assertIn('name="review_language"', index_html)
        self.assertIn('value="it"', index_html)
        self.assertIn('id="key" class="form-control" value="NF101"', index_html)

        question = {
            "question": "Question?",
            "answer_a": "A",
            "answer_b": "B",
            "answer_c": "C",
            "answer_d": "D",
            "picture_question": None,
            "picture_a": None,
            "picture_b": 202,
            "picture_c": None,
            "picture_d": None,
        }
        editor_context = {
            "request": request,
            "key": "NF101",
            "reference": question,
            "review": question,
            "reference_media": {
                "picture_question": None,
                "picture_a": None,
                "picture_b": "https://raw.githubusercontent.com/example/media/revision/202.de.svg",
                "picture_c": None,
                "picture_d": None,
            },
            "review_media": {
                "picture_question": None,
                "picture_a": None,
                "picture_b": "https://raw.githubusercontent.com/example/media/revision/202.fr.svg",
                "picture_c": None,
                "picture_d": None,
            },
            "diff": main.word_diff(
                {**question, "question": "Original question?"},
                question,
            ),
            "sha": "abc",
            "meta_sha": "def",
            "review_status": "to_be_reviewed",
            "review_status_author": "reviewer",
            "comments_sha": "",
            "comments": [],
            "reference_language": "de",
            "review_language": "fr",
            "reference_language_label": "German",
            "review_language_label": "French",
            "campaign_id": "default",
            "campaign_label": "Test campaign",
            "next_question": "NF102",
            "prev_question": None,
            "next_section": None,
            "prev_section": None,
        }
        editor_template = main.templates.get_template("editor.html")
        editor_html = editor_template.render(**editor_context)
        self.assertIn(
            "https://raw.githubusercontent.com/example/media/revision/202.fr.svg",
            editor_html,
        )
        self.assertNotIn("50ohm.uska.online", editor_html)
        self.assertIn("German (Reference)", editor_html)
        self.assertIn("diff removed", editor_html)
        self.assertIn("diff added", editor_html)
        self.assertIn(
            "/campaign/default/edit/NF102?reference_language=de&review_language=fr",
            editor_html,
        )
        self.assertIn(
            "/campaign/default/?reference_language=de&review_language=fr",
            editor_html,
        )
        self.assertIn("Campaign overview", editor_html)
        self.assertIn('value="commit">Commit</button>', editor_html)
        self.assertNotIn("Add comment", editor_html)
        self.assertIn('<div class="col-lg-8">\n            <h4>Edit Answers:</h4>', editor_html)
        self.assertIn('class="answer-edit-row d-flex align-items-start gap-2 mb-2"', editor_html)
        self.assertIn('for="answer-a">A</label>', editor_html)
        self.assertIn(
            'name="answer_a" class="form-control answer-textarea flex-grow-1" rows="2"',
            editor_html,
        )
        self.assertIn('name="comment" class="form-control" rows="3"', editor_html)
        layout_html = main.templates.get_template("layout.html").render(request=request)
        self.assertIn(f'/static/style.css?v={main.STATIC_VERSION}', layout_html)
        self.assertIn("Please wait. Working with GitHub...", layout_html)
        self.assertIn('aria-hidden="true" hidden', layout_html)
        self.assertIn('window.addEventListener("pageshow", hideBusyIndicator)', layout_html)
        self.assertIn("changed by reviewer", editor_html)

        editor_context["review_status"] = "approved"
        approved_html = editor_template.render(**editor_context)
        self.assertIn('value="reopen">Reopen</button>', approved_html)
        self.assertIn('name="question" class="form-control" rows="10" disabled', approved_html)
        self.assertIn(
            'name="answer_a" class="form-control answer-textarea flex-grow-1" rows="2" disabled',
            approved_html,
        )

    def test_commit_updates_text_comment_and_status(self) -> None:
        request = SimpleNamespace(
            session={"token": "test-token", "username": "reviewer"},
            query_params={"reference_language": "de", "review_language": "fr"},
        )
        meta = {
            "id": "q_111111111111",
            "review": {"de": "approved", "fr": "to_be_reviewed", "it": "to_be_reviewed"},
        }
        content = {
            "question_id": "q_111111111111",
            "language": "fr",
            "question": "Question?",
            "answer_a": "A",
            "answer_b": "B",
            "answer_c": "C",
            "answer_d": "D",
            "picture_question_url": None,
        }

        with (
            patch.object(
                main,
                "load_campaign",
                return_value=(
                    {},
                    None,
                    {"NF101": {"question_id": "q_111111111111"}},
                    "de",
                    "fr",
                ),
            ),
            patch.object(
                main,
                "fetch_path",
                side_effect=lambda campaign_id, ref, path, token: {
                    "pool/questions/q_111111111111/question.meta.json": {
                        "sha": "meta-sha",
                        "json": meta,
                    },
                    "pool/questions/q_111111111111/question.fr.json": {
                        "sha": "content-sha",
                        "json": content,
                    },
                    "reviews/q_111111111111.json": {
                        "sha": "new-comments-sha",
                        "json": {"comments": {"fr": ["Motif utile"]}},
                    },
                }[path],
            ),
            patch.object(main, "ensure_campaign_snapshot", return_value={"head_sha": "branch-head"}),
            patch.object(main, "fetch_optional_path", return_value=None),
            patch.object(main, "commit_campaign_files", return_value="new-head") as commit_files,
        ):
            response = main.save_question(
                request=request,
                campaign_id="default",
                key="NF101",
                sha="content-sha",
                meta_sha="meta-sha",
                comments_sha="",
                action="commit",
                question="Question corrigée?",
                answer_a="A",
                answer_b="B",
                answer_c="C",
                answer_d="D",
                comment="  Motif utile  ",
            )

        self.assertEqual(response.status_code, 303)
        commit_files.assert_called_once()
        campaign_id, changes, message, expected_head, token = commit_files.call_args.args
        self.assertEqual(campaign_id, "default")
        self.assertEqual(changes["pool/questions/q_111111111111/question.fr.json"]["question"], "Question corrigée?")
        self.assertEqual(changes["reviews/q_111111111111.json"]["comments"]["fr"], ["Motif utile"])
        self.assertEqual(changes["pool/questions/q_111111111111/question.meta.json"]["review"]["fr"], "approved")
        self.assertEqual(message, "Commit NF101 fr review")
        self.assertEqual(expected_head, "branch-head")
        self.assertEqual(token, "test-token")

    def test_reopen_changes_only_status(self) -> None:
        request = SimpleNamespace(
            session={"token": "test-token"},
            query_params={"reference_language": "de", "review_language": "fr"},
        )
        meta = {
            "id": "q_111111111111",
            "review": {"de": "approved", "fr": "approved", "it": "to_be_reviewed"},
        }
        with (
            patch.object(
                main,
                "load_campaign",
                return_value=(
                    {},
                    None,
                    {"NF101": {"question_id": "q_111111111111"}},
                    "de",
                    "fr",
                ),
            ),
            patch.object(
                main,
                "fetch_path",
                return_value={"sha": "meta-sha", "json": meta},
            ),
            patch.object(main, "ensure_campaign_snapshot", return_value={"head_sha": "branch-head"}),
            patch.object(main, "commit_campaign_files", return_value="new-head") as commit_files,
        ):
            response = main.save_question(
                request=request,
                campaign_id="default",
                key="NF101",
                sha="content-sha",
                meta_sha="meta-sha",
                comments_sha="",
                action="reopen",
            )

        self.assertEqual(response.status_code, 303)
        commit_files.assert_called_once()
        campaign_id, changes = commit_files.call_args.args[:2]
        self.assertEqual(campaign_id, "default")
        self.assertEqual(list(changes), ["pool/questions/q_111111111111/question.meta.json"])
        self.assertEqual(changes["pool/questions/q_111111111111/question.meta.json"]["review"]["fr"], "to_be_reviewed")

    def test_commit_rejects_stale_content_sha_without_writing(self) -> None:
        request = SimpleNamespace(
            session={"token": "test-token"},
            query_params={"reference_language": "de", "review_language": "fr"},
        )
        meta = {
            "id": "q_111111111111",
            "review": {"de": "approved", "fr": "to_be_reviewed"},
        }
        content = {
            "question_id": "q_111111111111",
            "language": "fr",
        }
        with (
            patch.object(
                main,
                "load_campaign",
                return_value=(
                    {},
                    None,
                    {"NF101": {"question_id": "q_111111111111"}},
                    "de",
                    "fr",
                ),
            ),
            patch.object(
                main,
                "fetch_path",
                side_effect=[
                    {"sha": "meta-sha", "json": meta},
                    {"sha": "new-content-sha", "json": content},
                ],
            ),
            patch.object(main, "ensure_campaign_snapshot", return_value={"head_sha": "branch-head"}),
            patch.object(main, "commit_campaign_files") as commit_files,
        ):
            response = main.save_question(
                request=request,
                campaign_id="default",
                key="NF101",
                sha="old-content-sha",
                meta_sha="meta-sha",
                comments_sha="",
                action="commit",
            )

        self.assertEqual(response.status_code, 409)
        commit_files.assert_not_called()

    def test_status_author_comes_from_commit_that_changed_language(self) -> None:
        commit = {
            "sha": "new",
            "parents": [{"sha": "old"}],
            "author": {"login": "status-reviewer"},
            "commit": {"author": {"name": "Fallback"}},
        }
        versions = {
            "new": {"sha": "new-blob", "json": {"review": {"fr": "approved"}}},
            "old": {"sha": "old-blob", "json": {"review": {"fr": "to_be_reviewed"}}},
        }
        with (
            patch.object(main, "STATUS_AUTHOR_CACHE", {}),
            patch.object(main, "fetch_path", return_value={"sha": "current-meta", "json": {}}),
            patch.object(main, "github_commits_for_path", return_value=[commit]),
            patch.object(
                main,
                "fetch_optional_path",
                side_effect=lambda campaign_id, ref, path, token: versions[ref],
            ),
        ):
            author = main.status_author("default", "question.meta.json", "fr", "token")

        self.assertEqual(author, "status-reviewer")

    def test_comments_are_attributed_to_their_introducing_commits(self) -> None:
        old_commit = {
            "sha": "old",
            "parents": [],
            "author": {"login": "first-reviewer"},
            "commit": {"author": {"name": "First"}},
        }
        new_commit = {
            "sha": "new",
            "parents": [{"sha": "old"}],
            "author": {"login": "second-reviewer"},
            "commit": {"author": {"name": "Second"}},
        }
        versions = {
            "campaign/test": {
                "sha": "current-blob",
                "json": {
                    "schema_version": 1,
                    "question_id": "q_111111111111",
                    "comments": {"fr": ["Premier", "Deuxième"]},
                },
            },
            "old": {
                "sha": "old-blob",
                "json": {"comments": {"fr": ["Premier"]}},
            },
            "new": {
                "sha": "new-blob",
                "json": {"comments": {"fr": ["Premier", "Deuxième"]}},
            },
        }
        with (
            patch.object(main, "github_commits_for_path", return_value=[new_commit, old_commit]),
            patch.object(
                main,
                "fetch_optional_path",
                side_effect=lambda campaign_id, ref, path, token: versions[ref],
            ),
        ):
            sha, comments = main.load_comments(
                "default", "q_111111111111", "fr", "token"
            )

        self.assertEqual(sha, "current-blob")
        self.assertEqual(comments[0]["author"], "first-reviewer")
        self.assertEqual(comments[1]["author"], "second-reviewer")

    def test_comment_append_preserves_other_languages(self) -> None:
        current = {
            "sha": "comments-sha",
            "json": {
                "schema_version": 1,
                "question_id": "q_111111111111",
                "comments": {"fr": ["Existant"]},
            },
        }
        payload = main.comment_with_append(
            current,
            "q_111111111111",
            "it",
            "Commento utile",
        )
        self.assertEqual(payload["comments"]["fr"], ["Existant"])
        self.assertEqual(payload["comments"]["it"], ["Commento utile"])


if __name__ == "__main__":
    unittest.main()
