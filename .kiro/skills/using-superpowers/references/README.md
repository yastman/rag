# Platform Tool Mapping References

These files map skill tool names to non-Kiro platform equivalents. They are
part of the upstream `using-superpowers` skill and ship for multi-platform
compatibility.

**Kiro-only deployments:** these files are unused at runtime. The active
`.kiro/skills/using-superpowers/SKILL.md` refers to them for cross-platform
users. They are kept here because `scripts/install_ready_skills.sh` installs
`using-superpowers` as a reference, and deleting them would cause drift on the
next `install_ready_skills.sh` run.

If this repo moves to Kiro-only and you want to prune, delete this directory
and remove the platform-mapping paragraph from `using-superpowers/SKILL.md`.
