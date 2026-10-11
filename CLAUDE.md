# USB-ISS App — shared rules for Claude Code

Two Claude Code instances work in this repo. The slash command you are given sets your role:

- `/build` → you are **vsclaude**, the builder. Follow `docs/roles/BUILDER.md`.
- `/review` → you are **revclaude**, the reviewer. Follow `docs/roles/REVIEWER.md`.

If you were given no role, ask Chris which one you are before changing anything.

A third Claude, **claude1** (a claude.ai project), owns product intent and audits the process at checkpoints. It has read-only access to the repo. Its memos arrive in `docs/process/checkpoints/`.

The process is a deliverable in its own right, alongside the app. Keep the records honest and complete.

## Sources of truth (highest priority first)
1. `docs/reference/usb-iss.pdf`: Devantech datasheet. Protocol bytes, modes, limits, timing.
2. `docs/SPEC.md`: what the app does.
3. `docs/DECISIONS.md`: how it is built, and why.
4. `docs/NEXT.md`: the current task.

If any two of these conflict, stop and report the conflict. Never resolve it silently.

## Hardware
- A USB-ISS is attached to this machine. Its port is read from `USB_ISS_PORT` (set in `.env`, which is not committed).
- Only one process can hold the port at a time. Never run hardware tests while the other instance might be running them.
- Hardware tests default to safe, read-only operations (version, serial number, mode set, I2C_TEST, GETPINS, GETAD). Driving outputs or writing to a downstream device is allowed only when `NEXT.md` asks for it explicitly.

## Workflow
- One iteration implements one `NEXT.md` task. Iterations are numbered NN (00, 01, …). Fix cycles reuse the same NN.
- The builder works on branch `iter/NN`. The reviewer merges to `main` and tags `iter-NN` only on Accept.
- All artifacts for an iteration go in `docs/iterations/NN/`.
- Raw test output goes to `docs/iterations/NN/logs/` and is written by the test runner itself. Never hand-edit a log, and never offer a summary in place of one.
- Process files (`CLAUDE.md`, `docs/roles/*`, `.claude/commands/*`, `docs/templates/*`) change only together with an entry in `docs/process/CHANGES.md`.

## Conventions
- Stack: TBD (see DECISIONS D-001).
- Commit messages: `iter NN: <summary>`.
- Add a new dependency only when `NEXT.md` or `DECISIONS.md` allows it.
