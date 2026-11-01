import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "src/qtranslate/audit/legacy.py"


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exists = MODULE.is_file()
        if cls.exists:
            spec = importlib.util.spec_from_file_location("key_audit", MODULE)
            cls.api = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.api)

    def api_ready(self):
        self.assertTrue(
            self.exists, "Missing credential audit/import/routing implementation"
        )
        return self.api

    def test_env_preserves_conflicting_models_and_account_bindings(self):
        api = self.api_ready()
        bundle = api.parse_env("""GOOGLE_LLM_MODEL_1=first-model
GOOGLE_LLM_MODEL_1=second-model
GOOGLE_API_KEY_1=google-test-secret-long
GOOGLE_API_KEY_1=google-test-secret-long
ACCOUNT_ID_1=account-one
CLOUDFLARE_API_KEY_1=same-cloudflare-test-secret
ACCOUNT_ID_2=account-two
CLOUDFLARE_API_KEY_2=same-cloudflare-test-secret
==DATALAB_API_KEY_1=datalab-test-secret-long==
# MODEL DEFINITIONS
GOOGLE_LLM_MODEL_2=third-model
# ACTIVE API KEYS
AIzaFakeLongKeyUsedOnlyInThisTest123456789
user: [someone@example.test](mailto:someone@example.test)
opaque-unattributed-secret-123456789
""")
        providers = {p["id"]: p for p in bundle["providers"]}
        self.assertEqual(
            providers["google"]["models"],
            ["first-model", "second-model", "third-model"],
        )
        self.assertEqual(len(providers["google"]["credentials"]), 3)
        self.assertEqual(
            {c["account_id"] for c in providers["cloudflare"]["credentials"]},
            {"account-one", "account-two"},
        )
        self.assertEqual(len(providers["datalab"]["credentials"]), 1)
        self.assertEqual(bundle["duplicates_removed"], 1)
        self.assertNotIn("someone@example.test", json.dumps(bundle["providers"]))

    def test_unknown_raw_token_is_not_assigned_to_a_provider(self):
        api = self.api_ready()
        bundle = api.parse_env("opaque-unattributed-secret-123456789\n")
        self.assertEqual(bundle["providers"], [])
        self.assertEqual(len(bundle["quarantine"]), 1)
        self.assertEqual(bundle["quarantine"][0]["reason"], "unknown_provider")

    def test_portable_roundtrip_is_private_and_rejects_unknown_schema(self):
        api = self.api_ready()
        bundle = api.parse_env("GOOGLE_API_KEY_1=fixture-only-secret-123456789\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.txt"
            api.write_private(path, bundle)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(api.load_bundle(path), bundle)
            path.write_text('{"format":"something-else","version":1}')
            with self.assertRaises(ValueError):
                api.load_bundle(path)

    def test_reports_and_errors_never_include_secrets(self):
        api = self.api_ready()
        secret = "fixture-secret-not-for-reports-123456"
        bundle = api.parse_env("GOOGLE_API_KEY_1=" + secret + "\n")
        safe = api.redact("upstream echoed " + secret, bundle)
        self.assertNotIn(secret, safe)
        report = api.blocked_report(bundle, {"google": "dns_failed"})
        self.assertNotIn(secret, json.dumps(report))
        self.assertIsNone(report["credentials"][0]["median_seconds"])
        self.assertEqual(report["credentials"][0]["status"], "network_blocked")
        self.assertEqual(report["rankings"], [])

    def test_ranking_ignores_failures_and_compares_matching_probes(self):
        api = self.api_ready()
        records = [
            {
                "provider": p,
                "credential_id": p + "-key",
                "model": "m",
                "status": "success",
                "seconds": s,
                "sample": i,
            }
            for p, times in [("slow", [3.0, 4.0, 5.0]), ("fast", [1.0, 2.0, 3.0])]
            for i, s in enumerate(times)
        ]
        records.append(
            {
                "provider": "broken",
                "credential_id": "bad",
                "model": "m",
                "status": "invalid_auth",
                "seconds": 0.01,
                "sample": 0,
            }
        )
        rankings = api.rank_records(records)
        self.assertEqual([r["provider"] for r in rankings], ["fast", "slow"])
        self.assertEqual(rankings[0]["median_seconds"], 2.0)
        self.assertEqual(rankings[0]["successful_samples"], 3)

    def test_sticky_success_survives_restart_and_fallback_is_key_first_circular(self):
        api = self.api_ready()
        bundle = api.parse_env("""GOOGLE_LLM_MODEL=m
GOOGLE_API_KEY_1=google-first-fixture-key
GOOGLE_API_KEY_2=google-second-fixture-key
OLLAMA_LLM_MODEL=o
OLLAMA_API_KEY_1=ollama-fixture-key
""")
        candidates = [
            {"provider": p["id"], "credential_id": c["id"], "model": p["models"][0]}
            for p in bundle["providers"]
            for c in p["credentials"]
        ]
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "routing.json"
            api.remember_success(state, "text", candidates[1])
            ordered = api.route_candidates(
                candidates, api.read_routing(state), "text", ["ollama", "google"]
            )
            self.assertEqual(ordered, [candidates[1], candidates[0], candidates[2]])
            self.assertEqual(
                api.route_candidates(candidates, {}, "text", ["ollama", "google"]),
                [candidates[2], candidates[0], candidates[1]],
            )

    def test_forbidden_auth_host_is_rejected_before_network(self):
        api = self.api_ready()
        with self.assertRaises(ValueError):
            api.request_json(
                "https://untrusted.invalid/api", {"Authorization": "Bearer fixture"}
            )

    def test_quota_and_permission_errors_are_never_invalid_credentials(self):
        api = self.api_ready()
        self.assertEqual(api.classify(401, {}), "invalid_auth")
        self.assertEqual(api.classify(403, {}), "permission_denied")
        self.assertEqual(api.classify(429, {}), "rate_limited")
        self.assertEqual(api.classify(402, {}), "quota_or_credit")
        self.assertEqual(api.classify(404, {}), "model_unavailable")

    def test_reasoning_only_and_truncated_responses_are_not_success(self):
        api = self.api_ready()
        self.assertEqual(
            api.output_text(
                "google",
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {"thought": True, "text": "hidden"},
                                    {"text": "Hello"},
                                ]
                            },
                        }
                    ]
                },
            ),
            "Hello",
        )
        self.assertEqual(
            api.output_text(
                "openrouter",
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": "half a sentence"},
                        }
                    ]
                },
            ),
            "",
        )
        self.assertEqual(
            api.output_text(
                "nvidia",
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"reasoning_content": "internal only"},
                        }
                    ]
                },
            ),
            "",
        )
        self.assertEqual(
            api.output_text("ollama", {"done": True, "message": {"content": "Hello"}}),
            "Hello",
        )
        self.assertEqual(
            api.output_text(
                "cloudflare",
                {"success": False, "result": {"response": "not successful"}},
            ),
            "",
        )

    def test_openrouter_discovery_keeps_free_cost_policy(self):
        api = self.api_ready()
        data = {
            "data": [
                {
                    "id": "some/paid",
                    "pricing": {"prompt": "0.01", "completion": "0.01"},
                },
                {"id": "some/free:free", "pricing": {"prompt": "0", "completion": "0"}},
            ]
        }
        self.assertEqual(api.discovered_models("openrouter", data), ["some/free:free"])

    def test_auxiliary_key_never_goes_to_another_providers_model_catalog(self):
        api = self.api_ready()
        with patch.object(
            api, "request_json", return_value=(200, {"data": []}, "")
        ) as request:
            with self.assertRaises(ValueError):
                api.model_catalog("jina", {"key": "fixture-jina-secret"}, 1)
            request.assert_not_called()

    def test_total_network_block_is_not_auth_failure_or_benchmark_time(self):
        api = self.api_ready()
        bundle = api.parse_env("GOOGLE_API_KEY_1=fixture-key-no-real-network\n")
        with patch.object(
            api.socket, "getaddrinfo", side_effect=OSError("test network blocked")
        ):
            report = api.audit(bundle)
        self.assertEqual(report["api_requests"], 0)
        self.assertEqual(report["attempts"], [])
        self.assertEqual(
            api.apply_audit(bundle, report)["providers"][0]["credentials"][0]["status"],
            "unverified",
        )

    def test_working_export_contains_only_proven_keys_and_models_no_quarantine(self):
        api = self.api_ready()
        self.assertTrue(
            hasattr(api, "working_bundle"), "Missing verified-only export filter"
        )
        bundle = api.parse_env("""GOOGLE_LLM_MODEL_1=unverified-model
GOOGLE_API_KEY_1=fixture-good-key
GOOGLE_API_KEY_2=fixture-unknown-key
GOOGLE_API_KEY_3=fixture-invalid-key
""")
        credentials = bundle["providers"][0]["credentials"]
        credentials[0].update(
            status="text_verified",
            verified_text_model="actually-working-model",
            thinking_disabled=True,
        )
        credentials[2]["status"] = "invalid_auth_confirmed"
        bundle["quarantine"].append({"value": "fixture-bad-key"})
        result = api.working_bundle(bundle)
        self.assertEqual(result["providers"][0]["models"], ["actually-working-model"])
        self.assertEqual(
            [c["key"] for c in result["providers"][0]["credentials"]],
            ["fixture-good-key"],
        )
        self.assertEqual(result["quarantine"], [])
        self.assertNotIn("fixture-unknown-key", json.dumps(result))
        self.assertNotIn("fixture-invalid-key", json.dumps(result))
        self.assertEqual(
            api.working_bundle(api.parse_env("GOOGLE_API_KEY_1=unknown-fixture-key\n"))[
                "providers"
            ],
            [],
        )

    def test_google_structured_invalid_key_is_not_a_model_error(self):
        api = self.api_ready()
        payload = {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "details": [{"reason": "API_KEY_INVALID", "domain": "googleapis.com"}],
            }
        }
        self.assertEqual(api.classify(400, payload), "invalid_auth")

    def test_model_timeout_can_fallback_to_another_configured_model(self):
        api = self.api_ready()
        bundle = api.parse_env(
            "GOOGLE_API_KEY_1=fixture-only-key\nGOOGLE_LLM_MODEL_1=slow\nGOOGLE_LLM_MODEL_2=fast\n"
        )

        def infer(provider, credential, model, sample, timeout):
            if model == "slow":
                raise TimeoutError("fixture timeout")
            return "success", "I am busy today. Can we meet tomorrow?", 200, ""

        with (
            patch.object(api, "network_preflight", return_value={}),
            patch.object(api, "infer", side_effect=infer),
        ):
            report = api.audit(bundle, repeats=1)
        self.assertEqual(report["credentials"][0]["status"], "text_verified")
        self.assertEqual(report["credentials"][0]["model"], "fast")

    def test_http_success_with_wrong_language_or_missing_meaning_is_not_working(self):
        api = self.api_ready()
        self.assertTrue(
            hasattr(api, "valid_probe_output"),
            "Missing task-specific benchmark validation",
        )
        self.assertTrue(api.valid_probe_output("I'm busy today. Can we meet tomorrow?"))
        self.assertTrue(api.valid_probe_output("I’m busy today. Can we meet tomorrow?"))
        self.assertFalse(
            api.valid_probe_output("Hôm nay mình bận. Có thể họp ngày mai không?")
        )
        self.assertFalse(api.valid_probe_output("I'm busy today."))

    def test_cloudflare_modern_models_return_choices_inside_result(self):
        api = self.api_ready()
        data = {
            "success": True,
            "result": {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "Full English result",
                            "reasoning_content": "not public",
                        },
                    }
                ]
            },
        }
        self.assertEqual(api.output_text("cloudflare", data), "Full English result")

    def test_thinking_off_is_sent_and_reasoning_output_is_rejected(self):
        api = self.api_ready()
        c = {"key": "fixture-key", "account_id": "fixture-account"}
        data = {
            "success": True,
            "result": {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "I am busy today. Can we meet tomorrow?",
                            "reasoning_content": "still thinking",
                        },
                    }
                ]
            },
        }
        with patch.object(api, "request_json", return_value=(200, data, "")) as request:
            status, _, _, _ = api.infer(
                "cloudflare", c, "@cf/google/gemma-4-26b-a4b-it", api.SAMPLES[0], 1
            )
        self.assertEqual(
            request.call_args.args[2].get("chat_template_kwargs"),
            {"enable_thinking": False},
        )
        self.assertEqual(status, "thinking_still_enabled")

    def test_export_does_not_reuse_old_thinking_enabled_benchmark(self):
        api = self.api_ready()
        bundle = api.parse_env(
            "GOOGLE_LLM_MODEL=model\nGOOGLE_API_KEY_1=fixture-secret-key\n"
        )
        bundle["providers"][0]["credentials"][0].update(
            status="text_verified", verified_text_model="model"
        )
        self.assertEqual(api.working_bundle(bundle)["providers"], [])

    def test_google_discovery_does_not_route_rewrites_to_audio_or_mandatory_thinking(
        self,
    ):
        api = self.api_ready()
        data = {
            "models": [
                {
                    "name": "models/" + m,
                    "supportedGenerationMethods": ["generateContent"],
                }
                for m in [
                    "gemini-2.5-flash-lite",
                    "gemini-2.5-flash-preview-tts",
                    "gemini-2.5-pro",
                    "gemini-3-flash-preview",
                ]
            ]
        }
        self.assertEqual(
            api.discovered_models("google", data), ["gemini-2.5-flash-lite"]
        )

    def test_clean_env_keeps_only_verified_credentials_and_private_exact_backup(self):
        api = self.api_ready()
        self.assertTrue(
            hasattr(api, "clean_env"), "Missing safe validated .env cleanup"
        )
        original = "GOOGLE_LLM_MODEL=m\nGOOGLE_API_KEY_1=fixture-valid-key\nGOOGLE_API_KEY_2=fixture-rejected-key\n"
        bundle = api.parse_env(original)
        bundle["providers"][0]["credentials"][0].update(
            status="text_verified", verified_text_model="m", thinking_disabled=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(original)
            backup = api.clean_env(path, bundle, Path(tmp) / ".secrets")
            self.assertEqual(Path(backup).read_text(), original)
            self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            cleaned = api.parse_env(path.read_text())
            self.assertEqual(
                [c["key"] for p in cleaned["providers"] for c in p["credentials"]],
                ["fixture-valid-key"],
            )
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                api.clean_env(path, api.empty_bundle(), Path(tmp) / ".secrets")
            self.assertEqual(path.read_bytes(), before)

    def test_later_reasoning_failure_disqualifies_verified_export(self):
        api = self.api_ready()
        bundle = api.parse_env("OLLAMA_API_KEY_1=fixture-key\nOLLAMA_LLM_MODEL=model\n")
        results = [
            ("success", "I am busy today. Can we meet tomorrow?", 200, ""),
            ("thinking_still_enabled", "text", 200, ""),
        ]
        with (
            patch.object(api, "network_preflight", return_value={}),
            patch.object(api, "infer", side_effect=results),
        ):
            report = api.audit(bundle, repeats=2)
        self.assertNotEqual(report["credentials"][0]["status"], "text_verified")
        self.assertEqual(
            api.working_bundle(api.apply_audit(bundle, report))["providers"], []
        )

    def test_configured_disallowed_cloudflare_model_is_not_probed_or_exported(self):
        api = self.api_ready()
        bundle = api.parse_env(
            "ACCOUNT_ID_1=account\nCLOUDFLARE_API_KEY_1=fixture-key\nCLOUDFLARE_LLM_MODEL=@cf/zai-org/glm-5.3-flash\n"
        )
        credential = bundle["providers"][0]["credentials"][0]
        credential.update(
            status="text_verified",
            verified_text_model="@cf/zai-org/glm-5.3-flash",
            thinking_disabled=True,
        )
        self.assertEqual(api.working_bundle(bundle)["providers"], [])
        with patch.object(api, "request_json") as request:
            status, *_ = api.infer(
                "cloudflare", credential, "@cf/zai-org/glm-5.3-flash", api.SAMPLES[0], 1
            )
        self.assertNotEqual(status, "success")
        request.assert_not_called()

    def test_explicit_google_thought_part_is_not_a_non_thinking_success(self):
        api = self.api_ready()
        data = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"thought": True, "text": "reasoning"},
                            {"text": "I am busy today. Can we meet tomorrow?"},
                        ]
                    },
                }
            ]
        }
        with patch.object(api, "request_json", return_value=(200, data, "")):
            status, *_ = api.infer(
                "google",
                {"key": "fixture-key"},
                "gemini-2.5-flash-lite",
                api.SAMPLES[0],
                1,
            )
        self.assertEqual(status, "thinking_still_enabled")

    def test_cli_rejects_inventory_source_and_export_collisions_before_writing(self):
        self.api_ready()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / ".env"
            original = "GOOGLE_API_KEY_1=fixture-key\n"
            source.write_text(original)
            out = Path(tmp) / "export.txt"
            command = [
                sys.executable,
                str(MODULE),
                "export",
                "--env",
                str(source),
                "--out",
                str(out),
                "--inventory",
                str(source),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_text(), original)
            self.assertFalse(out.exists())
            result = subprocess.run(
                command[:-1] + [str(out)], capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(out.exists())

    def test_one_account_quota_does_not_skip_an_independent_account(self):
        api = self.api_ready()
        bundle = api.parse_env("""CLOUDFLARE_LLM_MODEL=@cf/zai-org/glm-4.7-flash
ACCOUNT_ID_1=account-a
CLOUDFLARE_API_KEY_1=fixture-key-one
ACCOUNT_ID_2=account-b
CLOUDFLARE_API_KEY_2=fixture-key-two
ACCOUNT_ID_3=account-a
CLOUDFLARE_API_KEY_3=fixture-key-three
""")

        def infer(provider, c, model, sample, timeout):
            if c["key"] == "fixture-key-one":
                return (
                    "rate_limited",
                    "",
                    429,
                    {"scope": "account", "retry_after": "60"},
                )
            return "success", "I am busy today. Can we meet tomorrow?", 200, ""

        with (
            patch.object(api, "network_preflight", return_value={}),
            patch.object(api, "infer", side_effect=infer),
        ):
            result = api.audit(bundle, repeats=1)
        self.assertEqual(
            [r["status"] for r in result["credentials"]],
            ["rate_limited", "text_verified", "account_cooldown"],
        )

    def test_speed_ranking_excludes_a_pair_with_observed_quality_failure(self):
        api = self.api_ready()
        records = [
            {
                "provider": p,
                "credential_id": p,
                "model": "m",
                "status": s,
                "seconds": n,
                "sample": 0,
            }
            for p, s, n in [
                ("fast-but-wrong", "success", 0.01),
                ("fast-but-wrong", "task_validation_failed", 0.01),
                ("correct", "success", 1),
            ]
        ]
        self.assertEqual(
            [r["provider"] for r in api.rank_records(records)], ["correct"]
        )


if __name__ == "__main__":
    unittest.main()
