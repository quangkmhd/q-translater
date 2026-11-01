import argparse
import json
import sys
from dataclasses import asdict


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="qtranslate", description="Q Translate · Anh ↔ Việt trên Ubuntu GNOME"
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="Chạy backend nền")
    settings = commands.add_parser("settings", help="Mở dashboard")
    settings.add_argument("--smoke", action="store_true")
    chat = commands.add_parser("chat", help="Mở trợ lý Q-translate · Alt+D")
    chat.add_argument("--smoke", action="store_true")
    imp = commands.add_parser("import", help="Gộp key/model .env hoặc TXT")
    imp.add_argument("--file", required=True)
    exp = commands.add_parser("export", help="Xuất key/model đã kiểm tra")
    exp.add_argument("--file", required=True)
    commands.add_parser("status", help="Xem trạng thái backend/bridge")
    commands.add_parser("quit", help="Thoát backend")
    commands.add_parser("check", help="Kiểm tra môi trường desktop")
    audit = commands.add_parser("audit-keys", help="Công cụ audit độc lập")
    audit.add_argument("args", nargs=argparse.REMAINDER)
    args, extra = parser.parse_known_args(argv)
    if extra and args.command != "audit-keys":
        parser.error("Tham số không hợp lệ: " + " ".join(extra))
    try:
        if args.command == "chat":
            from .ui.chat import run_chat

            return run_chat(smoke=args.smoke)
        if args.command == "serve":
            from .app import run_service

            return run_service()
        if args.command in ("import", "export"):
            from .app import paths
            from .config.secrets import SecretStore
            from .config.env_import import parse_import

            config, _, _ = paths()
            store = SecretStore(config / "credentials.json")
            if args.command == "import":
                report = store.merge(parse_import(args.file))
                from .install import finish_setup
                from .config.settings import SettingsStore

                finish_setup(SettingsStore(config / "settings.json"))
                print(json.dumps(asdict(report)))
            else:
                store.export_verified(args.file)
                print("Đã xuất key/model đã kiểm tra.")
            return 0
        if args.command == "check":
            from .desktop.capabilities import collect_capabilities

            report = collect_capabilities().to_dict()
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report["status"] == "PASS" else 2
        if args.command in ("status", "quit"):
            from gi.repository import Gio, GLib

            method = "Stop" if args.command == "quit" else "Capabilities"
            try:
                reply = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
                    "org.qtranslate.App",
                    "/org/qtranslate/App",
                    "org.qtranslate.App1",
                    method,
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    2000,
                    None,
                )
            except GLib.Error:
                print(
                    "Backend chưa chạy hoặc không kết nối được session bus.",
                    file=sys.stderr,
                )
                return 2
            if args.command == "status":
                print(reply.unpack()[0])
            return 0
        if args.command == "audit-keys":
            from .audit import legacy

            sys.argv = ["qtranslate-audit", "audit", *extra, *args.args]
            legacy.main()
            return 0
        from .ui.dashboard import run_dashboard

        return run_dashboard(smoke=getattr(args, "smoke", False))
    except (ValueError, OSError, ImportError):
        print(
            "Không thể thực hiện. Kiểm tra đường dẫn, định dạng file hoặc Python hệ thống.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
