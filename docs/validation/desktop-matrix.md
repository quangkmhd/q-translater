# Desktop validation

2026-11-01. Release gate remains **BLOCKED**.

| Session | Extension / real selected GTK text | Terminal, browser, editor, Qt, PDF | XWayland | Mixed monitor scales / click-through |
|---|---|---|---|---|
| Ubuntu 24.04 GNOME 46 Xorg | Pending | Pending | N/A | Pending |
| Ubuntu 24.04 GNOME 46 Wayland | Pending | Pending | Pending | Pending |
| Ubuntu 26.04 GNOME 50 Wayland | Headless GTK PASS; real Orca/Codex Alt+V PASS | Orca plain terminal user-confirmed; Codex v0.166 real mouse PASS; other apps pending | X11 clipboard helper exercised; broader app matrix pending | Pending |

GNOME 50 headless is a real Mutter compositor with a virtual monitor and virtual input, not a user desktop acceptance run. Native probe creates a disposable GTK TextView, selects its synthetic Vietnamese text, presses Alt+V through Mutter RemoteDesktop, observes IPC streaming, reads actual clipboard and checks source unchanged. Evidence: [report](../../reports/native-desktop-e2e.json). TTFT 0.5601s; clipboard success 1.0475s in this single run, not a benchmark guarantee.

Capture probe has exercised actual Alt+X, drag selection, Shell.Screenshot stream and real vision API. See [report](../../reports/native-capture-e2e.json) for final status and exact assertions. This does not cover two displays or mixed scaling.

Still required: empty selection and stale PRIMARY when changing apps, terminal input/output, shortcut collisions, selection that predates extension activation, close/cancel/new invocation during stream and capture, outside click reaches destination exactly once, Alt+V focus persistence, long text scroll, image retry, HiDPI, Xorg and XWayland native application coverage. Candidate metadata permits GNOME46 loading for Ubuntu24 testing, based on tagged API inspection and version adapters. This is experimental eligibility, not a runtime support claim.

Real Orca/Codex: reports/real-codex-selection-verification.json, actual transcript mouse selection + Alt+V, source39chars is the new greeting while PRIMARY remains unchanged; streaming and full clipboard result pass. Alt+C source acquisition/preservation passes but that run hits FREE_RATE_LIMITED; source acquisition and provider success are reported separately.

Text-only popup update: reports/native-text-only-popup-e2e.json PASS on private GNOME50/native GTK. Observer sees no image actor for Alt+C/Alt+X. Outside clicks hide both and reach the underlying GTK button exactly once. Test submits the actual action adapters through an isolated fixture; vision input is a synthetic PNG, so this is not a new capture-selector acceptance claim. Real user source replays90/102chars now target English,17/324chars English target Vietnamese (azure-direction-user-replay.json). New UI is staged in the live user extension and requires one GNOME logout/login; backend direction fix is already active.
