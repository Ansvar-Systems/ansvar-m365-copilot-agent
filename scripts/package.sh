#!/usr/bin/env bash
# Build dist/ansvar-m365-copilot.zip from appPackage/.
#
# The ${AUTH_CONFIG_ID} placeholder in ai-plugin.json is replaced with the value
# of the AUTH_CONFIG_ID environment variable. That id comes from registering the
# OAuth client in the Teams Developer Portal and is not a committed value.
#
#   AUTH_CONFIG_ID=<oauth-config-id> ./scripts/package.sh
#
# Requires: python3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/appPackage"
DIST="$ROOT/dist"
OUT="$DIST/ansvar-m365-copilot.zip"

if [[ -z "${AUTH_CONFIG_ID:-}" ]]; then
  cat >&2 <<'MSG'
ERROR: AUTH_CONFIG_ID is not set.

Register the OAuth client in the Teams Developer Portal (Tools > OAuth client
registration), then pass the resulting configuration id:

  AUTH_CONFIG_ID=<oauth-config-id> ./scripts/package.sh
MSG
  exit 1
fi

# Guard against shipping a placeholder as if it were a real id.
case "$AUTH_CONFIG_ID" in
  *'${'* | *PLACEHOLDER* | *placeholder* | 00000000-0000-0000-0000-000000000000 | CHANGEME | changeme)
    echo "ERROR: AUTH_CONFIG_ID is still a placeholder: $AUTH_CONFIG_ID" >&2
    exit 1
    ;;
esac
if [[ ! "$AUTH_CONFIG_ID" =~ [^[:space:]] ]]; then
  echo "ERROR: AUTH_CONFIG_ID is blank." >&2
  exit 1
fi

mkdir -p "$DIST"
rm -f "$OUT"

PKG="$PKG" OUT="$OUT" AUTH_CONFIG_ID="$AUTH_CONFIG_ID" python3 - <<'PY'
import os
import zipfile

PKG = os.environ["PKG"]
OUT = os.environ["OUT"]
AUTH_CONFIG_ID = os.environ["AUTH_CONFIG_ID"]

# Exactly the files Microsoft expects, stored at the zip root.
MEMBERS = ["manifest.json", "declarativeAgent.json", "ai-plugin.json", "color.png", "outline.png"]

missing = [m for m in MEMBERS if not os.path.isfile(os.path.join(PKG, m))]
if missing:
    raise SystemExit(f"ERROR: missing from appPackage/: {', '.join(missing)}")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for member in MEMBERS:
        path = os.path.join(PKG, member)
        if member == "ai-plugin.json":
            text = open(path, encoding="utf-8").read()
            if "${AUTH_CONFIG_ID}" not in text:
                raise SystemExit("ERROR: ai-plugin.json has no ${AUTH_CONFIG_ID} placeholder to substitute.")
            zf.writestr(member, text.replace("${AUTH_CONFIG_ID}", AUTH_CONFIG_ID))
        else:
            zf.write(path, arcname=member)

with zipfile.ZipFile(OUT) as zf:
    names = zf.namelist()
    if any("/" in n for n in names):
        raise SystemExit(f"ERROR: zip members must sit at the root, got: {names}")
    print(f"built {OUT}")
    for info in zf.infolist():
        print(f"  {info.filename:24} {info.file_size:>7} bytes")
PY
