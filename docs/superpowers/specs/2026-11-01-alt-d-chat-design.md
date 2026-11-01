# Alt+D · Q-translate

User approved displayed image 1, renamed assistant **Q-translate**, and explicitly requested direct implementation.

- Compact floating native desktop chat, charcoal/lavender styling from the selected image. Header: name, new conversation, **Ẩn**, **×**. User messages on right, assistant on left, copy per reply; bottom multiline composer. Grow up to a bounded height, then scroll; keep composer visible.
- Alt+D opens/reopens the single chat window. Hide and Esc preserve draft, conversation and in-flight response. × cancels work, clears session history and destroys the window; next activation creates a new session. New conversation also clears/cancels the previous session. Outside click does not dismiss.
- Enter sends; Shift+Enter inserts a newline; IME preedit Enter commits text rather than sending. During a request expose Stop; do not enqueue another turn accidentally. Errors appear in the window; partial failed replies are not included in future model history.
- Actual general AI assistant: answer questions, translate, rewrite, explain grammar as requested; concise Vietnamese by default, no compulsory translation, no greetings/flattery/flowery prose, shortest sufficient answer. No reasoning output. Successful user/assistant pairs are passed as structured messages on every follow-up, including fallback. Never split a chat prompt into independent translation chunks.
- Reuse existing verified text providers, models, selected settings and sticky key-first/provider-after routing. Five seconds per complete key attempt; 30 seconds per turn total; streaming. No automatic clipboard writes.
- Session history lives only in RAM; closing the app ends it. Existing private diagnostic input/output/error logs remain under the already requested 24-hour clear policy; no saved chat-history database.
- Native GTK4 application, existing transport/engine, a small session model. LangGraph InMemorySaver/delete_thread docs were checked; a graph/checkpoint dependency adds no required capability for this single sequential conversation, so reuse the existing controller.
- GNOME custom Alt+D shortcut launches `qtranslate chat`, registered idempotently without replacing unrelated shortcuts; works immediately, independently of Shell extension reload. GTK's X11 backend works on Xorg and through existing XWayland on GNOME/Wayland; position this app's own window at the monitor's lower right. Do not automate desktop input.
- Add chat prompt and shortcut editing to existing settings; reuse text-provider settings. Preserve all Alt+C/V/X behavior. Build private-data-free Debian candidate and deploy user-local changes.

Implementation defaults: history survives hiding, not process restart; closing clears the chat session but does not erase the separate diagnostic log. No tools, file access, browser access or agent execution through chat.
