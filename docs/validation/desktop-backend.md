# Desktop backend

Python Gio service owns task state, settings and provider access. GNOME Shell extension owns global shortcuts, PRIMARY selection, CLIPBOARD writes, capture overlay and nonmodal St/Clutter popups. Keys never cross the desktop IPC interface.

Shell popups use top chrome, no modal grab; capture selection alone takes a temporary modal grab. Outside-click handler returns PROPAGATE. Alt+V waits for complete result and CopyText acknowledgment, then shows copy/check and starts its display deadline. Clipboard writes are gated by current task ID, backend unique owner and extension epoch.

Chosen Shell rendering over a Wayland GTK popup positioning workaround; headless GNOME50 runtime proves extension load, selected GTK source and Alt+V streaming/copy. It does not certify outside-click, scaling, XWayland or GNOME46 support. Runtime fixes discovered by real tests: StScrollable child wrapper, GNOME50 addTopChrome signature, Meta.SelectionType.SELECTION_PRIMARY, Gio/GLib Python bindings and timer argument order.

No Ctrl+C, Ctrl+V, Delete, Enter or editor mutation is sent to source applications. Sources lacking a readable/current PRIMARY selection yield an error and must be reselected; “every app” is not claimed without per-app evidence.
