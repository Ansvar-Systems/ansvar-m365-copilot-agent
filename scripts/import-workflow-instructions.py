#!/usr/bin/env python3
"""Import the generated workflow paragraphs into appPackage/declarativeAgent.json.

Two of the fourteen paragraphs in the agent's `instructions` field are GENERATED
by ansvar-workflow-mcp and consumed here verbatim: the one labelled `Workflows:`
and the one labelled `Reports and phase planning:`. They describe the workflow
loop and the report handoff, which are that server's contract to state, not this
repository's. Everything else in the field is hand-owned and this script never
touches it.

The chain is pinned end to end, so nothing reaches the package unverified:

    scripts/workflow-instructions.pin.json   commit + manifest sha + artifact sha
      -> git show <commit>:instructions/dist/manifest.json   sha must equal the pin
      -> the consumers[] entry with id `m365-workflows`
      -> git show <commit>:<that path>                       sha must equal the entry
      -> scripts/workflow-instructions.vendored.txt          the bytes, committed here
      -> the two labelled paragraphs of declarativeAgent.json

`--check` re-walks the last two links from the VENDORED copy alone, so it runs in
CI where no ansvar-workflow-mcp checkout exists and no network is available. It is
called from scripts/validate.sh, which makes drift a build failure.

  python3 scripts/import-workflow-instructions.py                 # import + vendor
  python3 scripts/import-workflow-instructions.py --check         # gate (CI)
  python3 scripts/import-workflow-instructions.py --check --verify-source
  python3 scripts/import-workflow-instructions.py --source /path/to/ansvar-workflow-mcp

RE-PINNING to a newer workflow-mcp release:

  1. Update `commit` AND `manifest_sha256` in the pin file TOGETHER. A commit moved
     without its manifest sha is an unverified import: the sha is the only thing
     that proves the artifact is the one that release generated.
  2. Run this script with no arguments. It rewrites `artifact_sha256`, the vendored
     copy, and the two paragraphs in one pass.
  3. Run ./scripts/validate.sh. The 8000-character instructions limit is the real
     ceiling here, and the generated paragraphs are the part that grows.
  4. Bump `version` in appPackage/manifest.json. A changed instructions field is a
     new app version.

DO NOT resubmit to Partner Center off the back of a re-pin on its own. Package
2.0.4 is under Microsoft validation (ticket #5636924) and the ratified founder
decision is: no Partner Center resubmission before Microsoft's go-ahead. Version
2.0.5 is STAGED in this repository and uploaded to nobody.

Requires: python3 (stdlib only) and git.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / "scripts" / "workflow-instructions.pin.json"
VENDORED = ROOT / "scripts" / "workflow-instructions.vendored.txt"
AGENT = ROOT / "appPackage" / "declarativeAgent.json"
DEFAULT_SOURCE = ROOT.parent / "ansvar-workflow-mcp"

MANIFEST_PATH = "instructions/dist/manifest.json"
CONSUMER_ID = "m365-workflows"

# The labels the artifact must carry, in the order it carries them. Splicing is
# BY LABEL, never by position, but the label set itself is the contract: a rename
# upstream has to be a deliberate change here, not a silent no-op or a mis-splice.
EXPECTED_LABELS = ("Workflows", "Reports and phase planning")

PARAGRAPH_SEP = "\n\n"


def fail(message: str) -> "None":
    """Every failure in this script is loud and fatal. There is no partial import."""
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_pin() -> dict:
    if not PIN.is_file():
        fail(f"pin file not found: {PIN}")
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    for key in ("repo", "commit", "manifest_sha256"):
        if not pin.get(key):
            fail(f"pin file is missing {key}")
    return pin


def git_show(source: Path, commit: str, path: str) -> str:
    """Read a blob from the pinned commit. Never from the checkout's working tree."""
    if not (source / ".git").exists():
        fail(f"--source is not a git checkout: {source}")
    proc = subprocess.run(
        ["git", "-C", str(source), "show", f"{commit}:{path}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail(
            f"could not read {path} at {commit[:12]} from {source}: "
            f"{proc.stderr.strip()}\n"
            f"      If the commit is unknown, run: git -C {source} fetch origin"
        )
    return proc.stdout


def artifact_from_source(source: Path, pin: dict) -> str:
    """Walk pin -> manifest -> consumer entry -> artifact, verifying both hashes."""
    manifest_raw = git_show(source, pin["commit"], MANIFEST_PATH)
    got = sha256(manifest_raw)
    if got != pin["manifest_sha256"]:
        fail(
            f"{MANIFEST_PATH} at {pin['commit'][:12]} hashes {got},\n"
            f"      pin says {pin['manifest_sha256']}.\n"
            f"      The commit and the manifest sha must be re-pinned together."
        )
    print(f"  [OK] manifest sha256 matches the pin ({got[:16]}...)")

    manifest = json.loads(manifest_raw)
    entries = [c for c in manifest.get("consumers", []) if c.get("id") == CONSUMER_ID]
    if len(entries) != 1:
        fail(
            f"expected exactly one consumers[] entry with id {CONSUMER_ID!r}, "
            f"found {len(entries)}"
        )
    entry = entries[0]
    for key in ("path", "sha256"):
        if not entry.get(key):
            fail(f"consumer {CONSUMER_ID!r} is missing {key}")

    artifact = git_show(source, pin["commit"], entry["path"])
    got = sha256(artifact)
    if got != entry["sha256"]:
        fail(
            f"{entry['path']} hashes {got}, manifest entry says {entry['sha256']}. "
            f"The upstream release is internally inconsistent; do not import it."
        )
    print(f"  [OK] artifact sha256 matches the manifest entry ({got[:16]}...)")
    print(f"  [OK] {entry['path']} ({len(artifact)} chars) read at {pin['commit'][:12]}")
    return artifact


def split_artifact(artifact: str) -> "dict[str, str]":
    """The artifact is exactly the labelled paragraphs, separated by a blank line."""
    paragraphs = artifact.split(PARAGRAPH_SEP)
    if len(paragraphs) != len(EXPECTED_LABELS):
        fail(
            f"artifact has {len(paragraphs)} paragraph(s), expected "
            f"{len(EXPECTED_LABELS)} separated by a blank line"
        )
    by_label = {}
    for label, paragraph in zip(EXPECTED_LABELS, paragraphs):
        if not paragraph.startswith(f"{label}:"):
            fail(
                f"artifact paragraph does not open with {label!r}: "
                f"{paragraph[:60]!r}\n"
                f"      An upstream label rename is a deliberate change here: update "
                f"EXPECTED_LABELS and the hand-owned paragraphs it collides with."
            )
        by_label[label] = paragraph
    return by_label


def load_field() -> "tuple[dict, list[str]]":
    agent = json.loads(AGENT.read_text(encoding="utf-8"))
    if "instructions" not in agent:
        fail(f"{AGENT} has no instructions field")
    return agent, agent["instructions"].split(PARAGRAPH_SEP)


def locate(paragraphs: "list[str]", label: str) -> int:
    """Exactly one paragraph must open with this label. Never append, never guess."""
    hits = [i for i, p in enumerate(paragraphs) if p.startswith(f"{label}:")]
    if len(hits) != 1:
        fail(
            f"expected exactly one paragraph starting {label + ':'!r} in "
            f"declarativeAgent.json, found {len(hits)}. The generated paragraphs are "
            f"REPLACED in place and are never appended: restore the labelled "
            f"paragraph before importing."
        )
    return hits[0]


def divergence(expected: str, actual: str) -> str:
    """A readable first-difference report. Character offsets, not a diff dump."""
    limit = min(len(expected), len(actual))
    at = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    start = max(0, at - 50)
    return (
        f"      first difference at character {at} "
        f"(pinned {len(expected)} chars, committed {len(actual)} chars)\n"
        f"      pinned   : ...{expected[start:at + 50]!r}\n"
        f"      committed: ...{actual[start:at + 50]!r}"
    )


def do_import(source: Path, pin: dict) -> int:
    print(f"== importing generated workflow instructions from {source} ==")
    artifact = artifact_from_source(source, pin)
    generated = split_artifact(artifact)

    agent, paragraphs = load_field()
    before_total = len(agent["instructions"])
    for label, paragraph in generated.items():
        index = locate(paragraphs, label)
        was = len(paragraphs[index])
        if paragraphs[index] == paragraph:
            print(f"  [OK] paragraph {index} {label!r} already current ({was} chars)")
            continue
        paragraphs[index] = paragraph
        print(f"  [--] paragraph {index} {label!r}: {was} -> {len(paragraph)} chars")

    agent["instructions"] = PARAGRAPH_SEP.join(paragraphs)
    # indent=2 plus a trailing newline reproduces the committed file byte for byte,
    # so an import shows up as a one-line diff on the instructions field alone.
    AGENT.write_text(json.dumps(agent, indent=2) + "\n", encoding="utf-8")
    VENDORED.write_text(artifact, encoding="utf-8")

    pin["artifact_sha256"] = sha256(artifact)
    PIN.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")

    total = len(agent["instructions"])
    print(f"  [OK] vendored {VENDORED.name} ({len(artifact)} chars)")
    print(f"  [OK] instructions field {before_total} -> {total} chars "
          f"({8000 - total} under the 8000 limit)")
    print("Imported. Run ./scripts/validate.sh, then bump appPackage/manifest.json.")
    return 0


def do_check(source: "Path | None", pin: dict) -> int:
    """Gate the committed field against the vendored artifact. No network, no source."""
    print("== checking generated workflow instructions against the pin ==")
    failures = []

    if not VENDORED.is_file():
        fail(f"vendored artifact not found: {VENDORED}. Run this script with no arguments.")
    artifact = VENDORED.read_text(encoding="utf-8")

    expected_sha = pin.get("artifact_sha256")
    if not expected_sha:
        fail("pin file has no artifact_sha256. Run this script with no arguments.")
    got = sha256(artifact)
    if got == expected_sha:
        print(f"  [PASS] {VENDORED.name} matches pin artifact_sha256 ({got[:16]}...)")
    else:
        print(f"  [FAIL] {VENDORED.name} hashes {got}, pin says {expected_sha}")
        failures.append("vendored artifact sha256")

    if source is not None:
        from_source = artifact_from_source(source, pin)
        if from_source == artifact:
            print(f"  [PASS] {VENDORED.name} matches {pin['commit'][:12]} in {source.name}")
        else:
            print(f"  [FAIL] {VENDORED.name} differs from the artifact at "
                  f"{pin['commit'][:12]}")
            print(divergence(from_source, artifact))
            failures.append("vendored artifact vs source")

    generated = split_artifact(artifact)
    _, paragraphs = load_field()
    for label, paragraph in generated.items():
        index = locate(paragraphs, label)
        if paragraphs[index] == paragraph:
            print(f"  [PASS] paragraph {index} {label!r} matches the pinned artifact "
                  f"({len(paragraph)} chars)")
        else:
            print(f"  [FAIL] paragraph {index} {label!r} has drifted from the pin")
            print(divergence(paragraph, paragraphs[index]))
            failures.append(f"paragraph {label!r}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} drift check(s): " + "; ".join(failures))
        print("The generated paragraphs are imported, never hand-edited. Either re-run")
        print("  python3 scripts/import-workflow-instructions.py")
        print("to restore them, or re-pin deliberately (see the header of that script).")
        return 1
    print("Generated workflow instructions are in sync with the pin.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import or verify the generated workflow paragraphs of the "
                    "declarative agent's instructions field.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"ansvar-workflow-mcp checkout to read the pinned commit from "
             f"(default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed paragraphs against the vendored artifact and exit "
             "non-zero on drift; needs no source checkout and no network",
    )
    parser.add_argument(
        "--verify-source",
        action="store_true",
        help="with --check, also re-derive the artifact from --source and compare it "
             "to the vendored copy (the full chain; not available in CI)",
    )
    args = parser.parse_args()

    if args.verify_source and not args.check:
        parser.error("--verify-source only applies with --check")

    pin = read_pin()
    if args.check:
        return do_check(args.source if args.verify_source else None, pin)
    return do_import(args.source, pin)


if __name__ == "__main__":
    raise SystemExit(main())
