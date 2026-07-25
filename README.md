# ansvar-m365-copilot-agent

The official Ansvar app for Microsoft 365 Copilot. It is a declarative agent that connects Copilot to the Ansvar MCP gateway at `https://gateway.ansvar.eu/mcp`, so a user can ask Copilot about European and United States law, regulation, and standards and get an answer that carries paragraph-level citations back to the official publisher.

This repository holds the app package submitted to Microsoft through Partner Center. It contains no application code. The agent is a set of manifests, and all retrieval happens in the gateway.

## Package layout

```
appPackage/
  manifest.json          Microsoft 365 app manifest (schema 1.25)
  declarativeAgent.json  name, description, instructions, conversation starters (schema v1.8)
  ai-plugin.json         API plugin manifest pointing at the MCP gateway (schema v2.4)
  color.png              192x192
  outline.png            32x32
assets/
  ansvar-mark.svg        the brand mark both icons are rendered from
scripts/
  render-icons.py        regenerates both icons from the mark
  validate.sh            schema, copy, and icon gate (also runs in CI)
  package.sh             builds dist/ansvar-m365-copilot.zip
```

The zip stores those five files at its root. Microsoft rejects a package whose members sit inside a folder.

## Tool discovery is dynamic, by design

`ai-plugin.json` declares a `RemoteMCPServer` runtime with `spec.url` and no `mcp_tool_description`. Under the v2.4 plugin schema, leaving the tool description out tells the runtime to call `tools/list` on the gateway at run time rather than use static definitions.

That is the shape this app needs, not a shortcut. The gateway scopes its tool surface to the signed-in user's subscription tier, so the tool list differs from user to user. Pinning tools in the manifest would advertise a fixed surface that does not match what a given user can call.

## Authentication

Every user authenticates as themselves, and the package carries no shared or embedded credentials.

- The gateway is an OAuth 2.1 resource server. Copilot runs the authorization code flow with PKCE against the Ansvar identity service at `https://auth.ansvar.eu`, realm `ansvar`.
- The Keycloak client is `m365-copilot`, with redirect URI `https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect`.
- The access token carries that user's own tier claim. The gateway decides from the token which corpora, tools, and workflows the call may reach, so entitlement is enforced server-side and not in the manifest.
- `reference_id` in `ai-plugin.json` holds the id of the OAuth client registration kept in the Teams Developer Portal. The client secret never enters this repository or the package.

## Building the package

`reference_id` is committed as the placeholder `${AUTH_CONFIG_ID}`. Register the OAuth client once in the Teams Developer Portal, under Tools then OAuth client registration, and pass the configuration id it hands back:

```bash
AUTH_CONFIG_ID=<oauth-config-id> ./scripts/package.sh
```

The script writes `dist/ansvar-m365-copilot.zip`. Three guards sit between a bad id and a built package:

- `AUTH_CONFIG_ID` must match `^[A-Za-z0-9+/=._-]{6,128}$` (the portal issues base64 registration IDs with a trailing `=`), which turns away an unset or blank value, whitespace, quotes, and angle brackets.
- It is refused when it contains `AUTH_CONFIG`, `YOUR`, `TODO`, `PLACEHOLDER`, or `CHANGEME` in any case, and when it is the all-zero GUID that `validate.sh` uses as its dummy.
- After substitution the script parses the result as JSON and asserts that `runtimes[0].auth.reference_id` equals the id it was handed, so a textual replace that produced invalid JSON, or that left the auth block untouched, fails the build.

Those guards catch an unresolved or malformed id, not a wrong one. A well-formed id pointing at the wrong registration still builds, and only sideloading the package will show it.

The zip is assembled and verified in a temp directory and moved into `dist/` only after it passes, so a failed build leaves the previous artifact where it was.

## Validating

```bash
./scripts/validate.sh
```

The gate needs `python3` with `jsonschema` and `pillow`, plus network access to fetch the three schemas. `AUTH_CONFIG_ID` is not required: the gate substitutes a dummy id, so the committed template is what gets validated. `.github/workflows/validate.yml` runs the same script on every push and pull request.

What it checks:

1. `manifest.json` and `declarativeAgent.json` against the unmodified published schemas. `ai-plugin.json` against the published v2.4 schema with one documented relaxation, described below.
2. The app name is identical across `manifest.json`, `declarativeAgent.json`, and `ai-plugin.json`. Store validation rejects the package when the three disagree.
3. Character limits on every length-capped field.
4. Copy rules on the store-facing and agent-visible text across all three files: no URLs, no non-ASCII characters, no marketing superlatives or ranking claims, no response-format commands, and none of the words banned by ADR-009.
5. Icon dimensions.
6. The packaging path, in CI: the workflow builds the zip with a throwaway auth id, then asserts the five members sit at the zip root, that the JSON members parse, and that `reference_id` carries the id it was given. That artifact is discarded and never uploaded.

The gate then prints a `[MANUAL]` line for each store rule it does not check, so a green run is not read as store readiness. Grammar, whether the two icons look like each other and like the brand, and whether the instructions produce good agent behavior are human checks. Microsoft-side acceptance is established by sideloading the built package and then by Partner Center review, not by schema conformance here.

### The one relaxation

The published v2.4 plugin schema defines `runtime.spec` as a `oneOf`, and its OpenAPI branch accepts a bare `{"url": ...}` exactly as the MCP branch does. A `RemoteMCPServer` that omits `mcp_tool_description` therefore matches two branches and fails `oneOf`, even though omitting it is how Microsoft documents dynamic tool discovery. The collision is specific to that shape: adding `mcp_tool_description` to pin tools makes the spec match the MCP branch alone and validate cleanly, so pinned-tool plugins never hit this.

`ai-plugin.json` keeps the documented dynamic-discovery form. `scripts/validate.sh` turns that single `oneOf` into an `anyOf` and then validates the spec against the one subschema its declared runtime type selects. Nothing else in the schema is touched.

## Icons

Both icons render from `assets/ansvar-mark.svg`, a copy of the shipped brand mark:

```bash
python3 scripts/render-icons.py
```

`color.png` sits the full mark inside the 120x120 safe region of a 192x192 violet plate. `outline.png` drops the wordmark and recenters the "AI" inside the frame, because at 32 pixels the wordmark aliases into an unreadable smear.

That makes the outline icon a simplification of the mark rather than a scaled copy of it, which is an accepted risk. If store review flags the two icons as mismatched, regenerate `outline.png` from the full mark and take the loss in legibility.

## License

MIT. See `LICENSE`.
