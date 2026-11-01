# Release candidate status

**Development candidate; not approved for release.** Files are implemented directly in the authorized workspace; there is no Git repository and no commit/merge/publish has occurred.

Implemented: Gio background service, GNOME46/50 candidate extension (runtime tested on GNOME50 only), three actions, streaming popup/copy, region-to-AI translation, GTK4 dashboard, verified per-key/model store, sticky/circular fallback, absolute deadlines, private 24h input/output/error log, portable merge/export, first-setup autostart and allowlisted Debian packaging.

Evidence and remaining gates:

- [Desktop matrix](desktop-matrix.md): GNOME50 headless native GTK selection/Alt+V passes. Ubuntu24 GNOME46, Xorg and monitor scaling remain pending. The real Ubuntu26 Orca/Codex selection path now passes; this does not certify all applications.
- [Providers](providers.md): real text and vision probes; Alt+C has successful live Google replays but later rate-limited responses; service availability remains variable.
- [Implementation ledger](implementation-ledger.md): RED→GREEN checkpoints, decisions, review and final verification.
- [README](../../README.md): source/package running instructions and data paths.

The `.deb` is an installable test artifact. Building it does not assert the unmet desktop/free-service acceptance gates. At the user’s subsequent request the app and extension were installed user-locally and run in the real GNOME session. No sudo system change was needed.

Final verification: **126 Python + 25 JavaScript tests PASS**; native source lint (legacy excluded), schemas, JS syntax, desktop entry validation and GTK dashboard smoke PASS. Package content scan: 48 files, no private artifacts or real credential matches; extracted CLI runs. See [package report](../../reports/package-check.json).

Fresh independent review completed; six Important findings fixed, two Minor findings re-graded and fixed for user-visible correctness (copy failure status and attempt deadline emissions). Deferred Minor: crop result still opens on the original app monitor when the crop is on another monitor.

Live Codex repair: reports/real-codex-selection-verification.json proves fresh internal TUI selection, successful streaming and copied result on actual Ubuntu26/Orca/Codex,4.185s. X11 ownership attribution, rich clipboard restoration and lost-acknowledgement cleanup have isolated regression tests. See tui-selection-research.txt for primary sources and compatibility limits.

Azure update: official Alt+C adapter, masked key/region setup and verified import/export deployed user-locally; live authenticated translation pending user F0 key. Browser creation remains blocked by saved Azure origin permissions. Backend error text carries setup guidance immediately without a Shell reload.

Supplied-key update: Azure Global real EN→VI, VI→EN and mixed→VI pass. Active key added to combined102-credential portable file; AI credentials retained. Key material excluded from package scan. F0 pricing tier is not inferred from the key.

Popup correction: Alt+X text only; Alt+C/Alt+X observe native Window user-time/current pointer events for dismissal, with stage handling and sampled fallback. Real isolated native click-through PASS; live UI pending GNOME relogin.
