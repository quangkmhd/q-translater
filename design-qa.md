# Alt+D native chat QA

Source visual truth: selected image 1, renamed Q-translate:
`/home/quangnhvn34/.codex/generated_images/01a1949a-40df-7d02-bf08-18866de2a321/exec-36f86a01-00c5-4b26-a61b-ca74faaddf79.png`.

Implementation: `docs/design/alt-d-native-result.png`, actual GTK4 widgets rendered on a private Xvfb display, not an HTML screenshot. Full comparison: `docs/design/alt-d-native-comparison.png`. Source panel cropped from 1486×1059 desktop image at approximately744×535 and normalized to540px width; implementation540×376 physical/CSS-equivalent pixels at scale1. Foreground result state matches the sample exchange; desktop background and generated-image shadow are excluded from fidelity judgments. The native Hide button is an explicitly requested addition after visual selection.

Fonts/typography: readable14–15px user/assistant text,17px title, compact supporting hints; native GTK/Pango rasterization rather than image-generator typography. Spacing: same right user bubble, plain left reply, copy below, bottom composer and compact top tools. Colors: existing charcoal/lavender tokens carried into native CSS, no extra result banners. Imagery: native symbolic icons rather than a rasterized interactive panel; no image assets required inside the chat. Copy: exact title Q-translate; concise assistant prompt, no automatic translation or forced greeting. These are a native implementation of the chosen component, not a clone of the background IDE.

Comparison history: initial capture exposed bottom controls clipped after resizing because placement read the previous native surface size. Repositioning on Gdk.Surface::layout fixed this; final capture540×376 shows the complete composer and send action. Native scale2 test with a100-line reply confirms window remains inside monitor bounds, composer remains mapped and transcript scrolls. Logical-to-X11-pixel conversion fixed the reviewer's HiDPI positioning reproduction.

Primary interactions tested with real GTK widgets: send/stream/complete, copy only on explicit click, hide/reactivate preserving draft and history, follow-up request context, new conversation, close/late response rejection, delayed transport cancellation and process cleanup, long-answer scroll and scale2 sizing. Real configured Cloudflare two-turn Engine test returned OK then the remembered synthetic marker in0.689s/0.468s. Installed app registered a live GTK application owner and a second real CLI launch reactivated that same owner. GNOME Alt+D binding readback succeeded. A physical Alt+D chord and real IBus/IME typing were not synthesized in this session; Enter uses GTK's documented IM-context filter. Ubuntu24/GNOME46 runtime matrix remains outside this one-machine validation.

Browser console is not applicable to the shipped native GTK feature. Native application/backend startup logs contain no traceback in the installed launch.

Findings: no remaining actionable P0/P1/P2 issue in the verified native flow.

final result: passed
