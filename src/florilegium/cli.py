from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: florilegium <crawl|download|audit> [args...]")
        return 1

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    if cmd == "crawl":
        from florilegium.workflows.crawl import main as crawl_main
        sys.argv = [sys.argv[0], *rest]
        return int(crawl_main())

    if cmd == "download":
        from florilegium.workflows.download import main as download_main
        sys.argv = [sys.argv[0], *rest]
        return int(download_main())

    if cmd == "audit":
        from florilegium.workflows.audit import main as audit_main
        sys.argv = [sys.argv[0], *rest]
        return int(audit_main())

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
