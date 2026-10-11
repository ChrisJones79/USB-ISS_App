# Decisions

Format: ID · date · status (adopted / pending Chris / pending claude1) · decision · rationale.

## D-001 · 2026-10-11 · adopted
Language and GUI stack: Python 3.12, PySide6, pyserial, pytest.
Rationale:
- Cross-platform.
- pyserial is the natural fit for the USB-ISS virtual COM port.
- pytest output can be captured directly into the iteration logs.

## D-002 · 2026-10-11 · adopted
Workflow: vsclaude builds, revclaude reviews and writes the next task, claude1 audits at checkpoints. See CLAUDE.md.

## D-003 · 2026-10-11 · adopted
Environment:
- pyenv pins Python 3.12 via a committed `.python-version` file.
- A project venv at `.venv/` (gitignored).
- Dependencies are listed in `pyproject.toml`.
- Never install into, or rely on, the system Python.

Rationale: both Claude Code instances and Chris must run identical interpreters and package versions. A shared system install hides drift.

## D-004 · 2026-10-11 · adopted
Card manifests are JSON (`card.json`). This avoids a YAML dependency, and the GUI card editor (F6) can write it using only the standard library.