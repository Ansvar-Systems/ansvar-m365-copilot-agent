#!/usr/bin/env bash
# Build dist/ansvar-m365-copilot.zip from appPackage/.
#
# The ${AUTH_CONFIG_ID} placeholder in ai-plugin.json is replaced with the value
# of the AUTH_CONFIG_ID environment variable. That id comes from registering the
# OAuth client in the Teams Developer Portal and is not a committed value.
#
#   AUTH_CONFIG_ID=<oauth-config-id> ./scripts/package.sh
#
# The build is atomic: the zip is assembled and verified in a temp directory and
# only then moved into dist/, so a failed build never replaces a good artifact.
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

# Shape check. Keeps out empty values, whitespace, quotes, angle brackets, and
# anything long enough to be a pasted blob rather than an id.
if [[ ! "$AUTH_CONFIG_ID" =~ ^[A-Za-z0-9._-]{6,64}$ ]]; then
  echo "ERROR: AUTH_CONFIG_ID must match ^[A-Za-z0-9._-]{6,64}\$ (got: '$AUTH_CONFIG_ID')." >&2
  exit 1
fi

# Deny-list for values that read as an unresolved instruction rather than an id.
lowered="${AUTH_CONFIG_ID,,}"
for token in auth_config authconfig your todo placeholder changeme; do
  if [[ "$lowered" == *"$token"* ]]; then
    echo "ERROR: AUTH_CONFIG_ID looks like a placeholder (contains '$token'): $AUTH_CONFIG_ID" >&2
    exit 1
  fi
done
if [[ "$AUTH_CONFIG_ID" == *"<"* || "$AUTH_CONFIG_ID" == *">"* ]]; then
  echo "ERROR: AUTH_CONFIG_ID must not contain angle brackets: $AUTH_CONFIG_ID" >&2
  exit 1
fi
# The all-zero GUID is the dummy validate.sh substitutes; it must never ship.
if [[ "$AUTH_CONFIG_ID" == "00000000-0000-0000-0000-000000000000" ]]; then
  echo "ERROR: AUTH_CONFIG_ID is the validation dummy, not a real id." >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PKG="$PKG" STAGE="$STAGE" AUTH_CONFIG_ID="$AUTH_CONFIG_ID" python3 - <<'PY'
import json
import os
import zipfile

PKG = os.environ["PKG"]
STAGE = os.environ["STAGE"]
AUTH_CONFIG_ID = os.environ["AUTH_CONFIG_ID"]

# Exactly the files Microsoft expects, stored at the zip root.
MEMBERS = ["manifest.json", "declarativeAgent.json", "ai-plugin.json", "color.png", "outline.png"]
JSON_MEMBERS = [m for m in MEMBERS if m.endswith(".json")]
PLACEHOLDER = "${AUTH_CONFIG_ID}"

missing = [m for m in MEMBERS if not os.path.isfile(os.path.join(PKG, m))]
if missing:
    raise SystemExit(f"ERROR: missing from appPackage/: {', '.join(missing)}")

# Substitute as text, then parse the result and assert the id landed in the field
# it belongs to. A textual replace alone could yield invalid JSON, or put the id
# somewhere harmless while auth quietly stayed a placeholder.
template = open(os.path.join(PKG, "ai-plugin.json"), encoding="utf-8").read()
if PLACEHOLDER not in template:
    raise SystemExit(f"ERROR: ai-plugin.json has no {PLACEHOLDER} placeholder to substitute.")
resolved = template.replace(PLACEHOLDER, AUTH_CONFIG_ID)

try:
    parsed = json.loads(resolved)
except json.JSONDecodeError as exc:
    raise SystemExit(f"ERROR: substituted ai-plugin.json is not valid JSON: {exc}") from exc

reference_id = parsed["runtimes"][0]["auth"]["reference_id"]
if reference_id != AUTH_CONFIG_ID:
    raise SystemExit(
        f"ERROR: runtimes[0].auth.reference_id is {reference_id!r}, expected {AUTH_CONFIG_ID!r}."
    )
if PLACEHOLDER in resolved:
    raise SystemExit(f"ERROR: {PLACEHOLDER} still present after substitution.")

staged = os.path.join(STAGE, "ansvar-m365-copilot.zip")
with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as zf:
    for member in MEMBERS:
        if member == "ai-plugin.json":
            zf.writestr(member, resolved)
        else:
            zf.write(os.path.join(PKG, member), arcname=member)

# Verify the artifact before it is allowed anywhere near dist/.
with zipfile.ZipFile(staged) as zf:
    names = zf.namelist()
    if names != MEMBERS:
        raise SystemExit(f"ERROR: zip must contain exactly {MEMBERS} at the root, got {names}")
    if any("/" in n for n in names):
        raise SystemExit(f"ERROR: zip members must sit at the root, got: {names}")
    for member in JSON_MEMBERS:
        try:
            json.loads(zf.read(member).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ERROR: {member} in the zip is not valid JSON: {exc}") from exc
    built = json.loads(zf.read("ai-plugin.json").decode("utf-8"))
    if built["runtimes"][0]["auth"]["reference_id"] != AUTH_CONFIG_ID:
        raise SystemExit("ERROR: reference_id in the built zip does not match AUTH_CONFIG_ID.")
    print("verified staged artifact:")
    for info in zf.infolist():
        print(f"  {info.filename:24} {info.file_size:>7} bytes")
PY

# Only now replace the previous artifact.
mkdir -p "$DIST"
mv "$STAGE/ansvar-m365-copilot.zip" "$OUT"
echo "built $OUT"
