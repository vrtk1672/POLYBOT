from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.security.env_audit import build_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe POLYBOT env audit. Never prints raw secret values.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--no-masked-values", action="store_true", help="Hide even masked values.")
    args = parser.parse_args()
    payload = build_audit(include_masked=not args.no_masked_values)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"safe_env_audit status={payload['safe_config_guard_status']} raw_values_printed=false")
        print(f"duplicate_env_keys={','.join(payload['duplicate_env_keys']) or 'NONE'}")
        print(f"dangerous_duplicate_overrides={','.join(payload['dangerous_duplicate_overrides']) or 'NONE'}")
        for key, status in payload["key_status"].items():
            suffix = f" masked={status['masked']}" if status.get("masked") else ""
            print(f"{key}: {status['status']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

