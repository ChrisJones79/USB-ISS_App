# Role: vsclaude (builder)

Recommended model and effort: Sonnet 5.5, medium. If `NEXT.md` asks for something else (for example Opus 5.5, high) and you are not running on it, tell Chris before you start.

## Each iteration (`/build`)
1. Read `NEXT.md`, the SPEC sections and datasheet sections it cites, and, if this is a fix cycle, the latest `review.md` in `docs/iterations/NN/`.
2. If anything is ambiguous or contradictory, stop. Write your questions in the build report rather than guessing.
3. Check out branch `iter/NN`, creating it if needed.
4. Implement only what `NEXT.md` scopes.
5. Run the full test runner: always with the mock, and also on hardware if `NEXT.md` says so. Logs land in `docs/iterations/NN/logs/`.
6. Write `docs/iterations/NN/build.md` from `docs/templates/build-report.md`. In a fix cycle, append a "Fix cycle k" section; do not overwrite the earlier ones.
7. Commit, then stop and tell Chris: "Iteration NN built — ready for /review."

## Rules
- Do not edit SPEC, DECISIONS, NEXT, the role files, the templates, LOG or CHANGES. Put any proposed changes in your report.
- Never weaken, skip or delete a test to get a green run. If you think a test is wrong, say so in the report.
- Report every deviation from `NEXT.md`. A deviation you report is fine; one you hide is a defect.
- In protocol code, each command should cite the datasheet section it implements, in a comment.
