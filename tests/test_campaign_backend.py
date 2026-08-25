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


if __name__ == "__main__":
    unittest.main()
