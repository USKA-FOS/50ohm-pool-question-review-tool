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
    def test_original_question_uses_immutable_canonical_source(self) -> None:
        manifest = {
            "canonical_source": {
                "repository": "USKA-FOS/50ohm-question-pool",
                "revision": "canonical-commit",
                "pool_path": "pool",
            }
        }
        expected = {"sha": "original-sha", "json": {"question": "Original?"}}

        with patch.object(main, "fetch_repository_path", return_value=expected) as fetch:
            result = main.fetch_original_question(
                manifest,
                "q_111111111111",
                "fr",
                "token",
            )

        self.assertEqual(result, expected)
        fetch.assert_called_once_with(
            "USKA-FOS/50ohm-question-pool",
            "canonical-commit",
            "pool/questions/q_111111111111/question.fr.json",
            "token",
        )

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
                    "review": {"de": "approved", "fr": "approved"},
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
        }

        with patch.object(
            main,
            "fetch_path",
            side_effect=lambda ref, path, token: {"sha": path, "json": payloads[path]},
        ):
            loaded_manifest, campaign_toc, questions, reference_language, review_language = main.load_campaign(
                "token"
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
        restricted_manifest = {
            "languages": ["de", "fr", "it"],
            "editable_languages": ["fr", "it"],
        }
        with self.assertRaisesRegex(ValueError, "not editable"):
            main.select_languages(restricted_manifest, "fr", "de")

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
            language_labels=main.LANGUAGE_LABELS,
        )
        self.assertIn('name="reference_language"', index_html)
        self.assertIn('name="review_language"', index_html)
        self.assertIn('value="it"', index_html)

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
            "next_question": "NF102",
            "prev_question": None,
            "next_section": None,
            "prev_section": None,
        }
        editor_template = main.templates.get_template("editor.html")
        editor_html = editor_template.render(**editor_context)
        self.assertIn("images_fr/202.svg", editor_html)
        self.assertIn("German (Reference)", editor_html)
        self.assertIn("diff removed", editor_html)
        self.assertIn("diff added", editor_html)
        self.assertIn(
            "/edit/NF102?reference_language=de&review_language=fr",
            editor_html,
        )
        self.assertIn('value="commit">Commit</button>', editor_html)
        self.assertNotIn("Add comment", editor_html)
        layout_html = main.templates.get_template("layout.html").render(request=request)
        self.assertIn("Please wait. Working with GitHub...", layout_html)
        self.assertIn('aria-hidden="true" hidden', layout_html)
        self.assertIn('window.addEventListener("pageshow", hideBusyIndicator)', layout_html)
        self.assertIn("changed by reviewer", editor_html)

        editor_context["review_status"] = "approved"
        approved_html = editor_template.render(**editor_context)
        self.assertIn('value="reopen">Reopen</button>', approved_html)
        self.assertIn('name="question" class="form-control" rows="10" disabled', approved_html)

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
                side_effect=[
                    {"sha": "meta-sha", "json": meta},
                    {"sha": "content-sha", "json": content},
                ],
            ),
            patch.object(main, "fetch_optional_path", return_value=None),
            patch.object(main, "update_path") as update_path,
        ):
            response = main.save_question(
                request=request,
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
        self.assertEqual(update_path.call_count, 3)
        content_call, comment_call, meta_call = [call.args for call in update_path.call_args_list]
        self.assertEqual(content_call[0], "pool/questions/q_111111111111/question.fr.json")
        self.assertEqual(content_call[1]["question"], "Question corrigée?")
        self.assertEqual(comment_call[0], "reviews/q_111111111111.json")
        self.assertEqual(comment_call[1]["comments"]["fr"], ["Motif utile"])
        self.assertEqual(meta_call[0], "pool/questions/q_111111111111/question.meta.json")
        self.assertEqual(meta_call[1]["review"]["fr"], "approved")

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
            patch.object(main, "update_path") as update_path,
        ):
            response = main.save_question(
                request=request,
                key="NF101",
                sha="content-sha",
                meta_sha="meta-sha",
                comments_sha="",
                action="reopen",
            )

        self.assertEqual(response.status_code, 303)
        update_path.assert_called_once()
        args = update_path.call_args.args
        self.assertEqual(args[0], "pool/questions/q_111111111111/question.meta.json")
        self.assertEqual(args[1]["review"]["fr"], "to_be_reviewed")

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
            patch.object(main, "update_path") as update_path,
        ):
            response = main.save_question(
                request=request,
                key="NF101",
                sha="old-content-sha",
                meta_sha="meta-sha",
                comments_sha="",
                action="commit",
            )

        self.assertEqual(response.status_code, 409)
        update_path.assert_not_called()

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
            patch.object(main, "github_commits_for_path", return_value=[commit]),
            patch.object(main, "fetch_optional_path", side_effect=lambda ref, path, token: versions[ref]),
        ):
            author = main.status_author("question.meta.json", "fr", "token")

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
            main.CAMPAIGN_BRANCH: {
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
            patch.object(main, "fetch_optional_path", side_effect=lambda ref, path, token: versions[ref]),
        ):
            sha, comments = main.load_comments("q_111111111111", "fr", "token")

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
