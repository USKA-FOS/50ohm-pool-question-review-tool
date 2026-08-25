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

    def test_approval_changes_only_requested_review_status(self) -> None:
        meta = {
            "id": "q_111111111111",
            "review": {"de": "approved", "fr": "to_be_reviewed", "it": "rejected"},
            "external_refs": [],
        }

        approved = main.approved_meta(meta, "q_111111111111", "fr")

        self.assertEqual(approved["review"]["fr"], "approved")
        self.assertEqual(approved["review"]["it"], "rejected")
        self.assertEqual(meta["review"]["fr"], "to_be_reviewed")

    def test_approval_only_stage_detects_submitted_text_changes(self) -> None:
        current = {
            "question": "Question?",
            "answer_a": "A",
            "answer_b": None,
            "answer_c": "",
            "answer_d": "D",
        }

        self.assertTrue(main.submitted_text_is_unchanged(current, "Question?", "A", None, None, "D"))
        self.assertFalse(main.submitted_text_is_unchanged(current, "Changed?", "A", None, None, "D"))
        self.assertFalse(main.submitted_text_is_unchanged(current, "Question?", "A", "B", None, "D"))

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

    def test_language_selection_uses_manifest_and_requires_distinct_languages(self) -> None:
        manifest = {
            "languages": ["de", "fr", "it"],
            "editable_languages": ["fr", "it"],
        }

        self.assertEqual(main.select_languages(manifest), ("de", "fr"))
        self.assertEqual(main.select_languages(manifest, "fr", "it"), ("fr", "it"))
        with self.assertRaisesRegex(ValueError, "not editable"):
            main.select_languages(manifest, "fr", "de")
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            main.select_languages(manifest, "fr", "fr")

    def test_templates_render_and_preserve_dynamic_language_query(self) -> None:
        request = SimpleNamespace(session={"token": "test-token"})
        index_html = main.templates.get_template("index.html").render(
            request=request,
            logged_in=True,
            toc=[],
            rate_limit_json=None,
            languages=["de", "fr"],
            editable_languages=["fr"],
            reference_language="de",
            review_language="fr",
            language_labels=main.LANGUAGE_LABELS,
        )
        self.assertIn('name="reference_language"', index_html)
        self.assertIn('name="review_language"', index_html)

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
        editor_html = main.templates.get_template("editor.html").render(
            request=request,
            key="NF101",
            reference=question,
            review=question,
            diff=main.word_diff(question, question),
            sha="abc",
            meta_sha="def",
            review_status="to_be_reviewed",
            reference_language="de",
            review_language="fr",
            reference_language_label="German",
            review_language_label="French",
            next_question="NF102",
            prev_question=None,
            next_section=None,
            prev_section=None,
        )
        self.assertIn("images_fr/202.svg", editor_html)
        self.assertIn(
            "/edit/NF102?reference_language=de&review_language=fr",
            editor_html,
        )

    def test_save_approves_metadata_without_writing_question_text(self) -> None:
        request = SimpleNamespace(
            session={"token": "test-token", "username": "reviewer"},
            query_params={"reference_language": "de", "review_language": "fr"},
        )
        content = {
            "question_id": "q_111111111111",
            "language": "fr",
            "question": "Question?",
            "answer_a": "A",
            "answer_b": "B",
            "answer_c": "C",
            "answer_d": "D",
        }
        meta = {
            "id": "q_111111111111",
            "review": {"de": "approved", "fr": "to_be_reviewed", "it": "to_be_reviewed"},
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
                    {"sha": "content-sha", "json": content},
                    {"sha": "meta-sha", "json": meta},
                ],
            ),
            patch.object(main, "update_path") as update_path,
        ):
            response = main.save_question(
                request=request,
                key="NF101",
                sha="content-sha",
                meta_sha="meta-sha",
                question="Question?",
                answer_a="A",
                answer_b="B",
                answer_c="C",
                answer_d="D",
                comment=None,
            )

        self.assertEqual(response.status_code, 303)
        update_path.assert_called_once()
        args = update_path.call_args.args
        self.assertEqual(args[0], "pool/questions/q_111111111111/question.meta.json")
        self.assertEqual(args[1]["review"]["fr"], "approved")
        self.assertEqual(args[2], "meta-sha")

    def test_save_rejects_stale_sha_without_writing(self) -> None:
        request = SimpleNamespace(
            session={"token": "test-token"},
            query_params={"reference_language": "de", "review_language": "fr"},
        )
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
                    {"sha": "new-content-sha", "json": {}},
                    {"sha": "meta-sha", "json": {}},
                ],
            ),
            patch.object(main, "update_path") as update_path,
        ):
            response = main.save_question(
                request=request,
                key="NF101",
                sha="old-content-sha",
                meta_sha="meta-sha",
                question="Question?",
            )

        self.assertEqual(response.status_code, 409)
        update_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
