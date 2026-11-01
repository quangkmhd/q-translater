# Azure Translator for Alt+C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans; implement directly in the authorized workspace.

**Goal:** Replace the default unreliable unauthenticated web translation path with official Azure Translator standard NMT, configured using a user-created Free F0 resource.
**Architecture:** Keep GNOME selection/popups and AI rewriting/vision unchanged. Add one HTTPS Azure adapter, translation-only credentials in the existing private store, and masked dashboard setup/test/import/export. Azure must be the default even when no key exists: show setup guidance, never silently call web endpoints or LLMs.
**Tech Stack:** Existing Python/Gio/GTK4/GNOME extension; stdlib document HTTPS transport.
**Spec:** User accepted the proposed Azure Translator F0 switch in conversation; implementation decisions below complete that small design without another approval round.

## Design and approaches
- Chosen: Azure official standard NMT with an explicit user key, region optional for global resources. Existing Google/Bing web endpoints are unreliable; LLM substitution conflicts with Alt+C's translation-service requirement.
- Current environment has no Azure key/resource. User is creating Free F0 manually; no account creation, paid tier upgrade, or claim of successful authenticated live translation without their key.
- Key is verified by a small synthetic translation before dashboard save. Imported unverified keys remain pending and excluded from runtime/export until checked. Merge by key+region; multiple verified keys fall back once each and reuse last successful pair.
- Azure standard /translate v3.0 global endpoint; subscription key in header, optional region header, no credentials in argv/logs. No custom/paid LLM deployment or tier-management API. The app cannot infer Azure pricing tier from a key; user must choose F0 in Azure.
- Preserve EN↔VI/mixed→VI behavior, explicit target override, all source text through bounded chunks, no output truncation; 5s per key/attempt and 30s overall including existing acquisition. Distinct missing key, auth/region, forbidden, quota, throttle, network and timeout errors.

## Global constraints
- No .git exists: no Git initialization/commit/worktree. Keep existing private keys intact.
- No real key in source, examples, package, screenshots, tool output, or command arguments.
- No silent fallback to Google/Bing/LLM; UI still uses the existing approved popup.

## Review focus
- A 401 is not quota exhaustion; 403001 and 429 must differ.
- Region-specific key identity survives import/export/deduplication; global omits region header.
- Missing key never sends user text anywhere; pending imports never enter runtime.
- Cancel/deadline during fallback or long chunks discards partial success.
- Existing LLM audit/import ignores Azure translation-only credentials.

### Task 1: Credentials and official translation runtime
Files: config/secrets.py, config/env_import.py, settings.py, providers/azure_translator.py, providers/http.py, actions/__init__.py; tests/unit/test_azure_translator.py.
- [x] Write and run RED tests for private merge/export, env imports and missing-key routing.
- [x] Add native translation credentials without extending the legacy AI audit provider list.
- [x] Write and run RED transport-boundary tests: key/region/body/url, directions, chunk completeness, error mapping, fallback/sticky, cancellation/deadline.
- [x] Implement Azure adapter with the existing cancellable HTTPS document transport and exact allowlisted hostname.
- [x] Switch Alt+C default route; run unit and full suites.

### Task 2: Dashboard, error copy and user-local deployment
Files: ui/model.py, ui/dashboard.py, extension/popups.js, docs, safe example env and package.
- [x] RED model tests for verify-before-save, failure preserving prior configuration, pending import verification and masked status.
- [x] Add Alt+C setup card: password field, region/global, Test & Save, pending-key verification and portal link. Explain F0 selection and missing key.
- [x] Distinct concise Vietnamese popup errors; preserve current window behavior.
- [x] Full tests/lint/schema/JS checks; isolated GTK smoke. Independent focused review and fix important findings.
- [x] Build and scan Debian artifact for private members/real keys. Deploy user-local backend/UI/extension error map safely; prove live missing-key behavior. If user supplies a key, run a real short EN/VI translation and record metrics only.

Execution result: implementation/deployment and isolated checks complete; actual Azure resource creation/key-backed live translation remain blocked by saved browser origin permission and absent user F0 key. No resource or key was fabricated.
