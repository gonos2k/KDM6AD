# Schema Status

Formal kg schema files are installed and pinned for this vault.

- Pin: `wiki/.schema/pin.yaml`
- Source: local `kg-skill` bundle mirrored from the upstream Claude-oriented repository
- Codex runtime copies: `/Users/yhlee/.agents/skills/kg/`, `/Users/yhlee/.codex/skills/kg/`, `/Users/yhlee/.Codex/skills/kg/`

The upstream instructions mention `~/.claude/skills/kg/`; in this workspace the
schema/templates were also copied to Codex-readable skill directories so future
`$kg-init` style workflows do not depend on the Claude-only path.
