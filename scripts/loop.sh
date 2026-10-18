#!/usr/bin/env bash
# Automated build -> review loop between claude1 checkpoints (CP-01, CHANGES v3).
#
# Run from a plain terminal in the repo root, on an up-to-date main:
#     ./scripts/loop.sh
# Optional environment:
#     MAX_ACCEPTS=4        stop after this many accepted iterations (default 4)
#     NTFY_TOPIC=<topic>   also push stop notices to https://ntfy.sh/<topic>
#     BUILDER_MODEL / REVIEWER_MODEL   defaults: sonnet / opus
#     RESUME_REVIEW=iter/NN  skip the first build and start by reviewing that existing branch
#                            (use after a stop that happened between a finished build and its review)
#
# The loop never touches the bench. It stops and notifies on: a Rethink, a checkpoint,
# a second consecutive Fix, a builder blocker, a reviewer "needs_chris", a NEXT whose hardware
# section goes beyond safe-read, a DECISIONS entry pending claude1, or any unexpected state.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)" || exit 1
cd "$ROOT"

MAX_ACCEPTS="${MAX_ACCEPTS:-4}"
BUILDER_MODEL="${BUILDER_MODEL:-sonnet}"
REVIEWER_MODEL="${REVIEWER_MODEL:-opus}"
SETTINGS=".claude/loop-settings.json"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
WORK=".loop/$STAMP"                     # gitignored while running
mkdir -p "$WORK"
RUNLOG="$WORK/run.log"

say()    { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$RUNLOG"; }
notify() {
  say "STOP: $*"
  command -v notify-send >/dev/null 2>&1 && notify-send "USB-ISS loop" "$*" || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -fsS -m 10 -d "USB-ISS loop: $*" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
}
finish() {
  # Archive this run's records on main so claude1 can audit them.
  local why="$1"
  notify "$why"
  if [ -z "$(git status --porcelain)" ] && git checkout -q main; then
    mkdir -p docs/process/loop
    cp -r "$WORK" "docs/process/loop/$STAMP"
    git add "docs/process/loop/$STAMP" && git commit -q -m "loop: run record $STAMP ($why)" \
      && git push -q origin main && say "run record committed to docs/process/loop/$STAMP"
  else
    say "tree not clean or main not checked out; run record left in $WORK (not committed)"
  fi
  exit 0
}
# --output-format json may be a single result object or (CLI 2.1.295) the full message list; use the "result" message.
json_field() { python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
if isinstance(d, list):
    d=next((m for m in reversed(d) if isinstance(m, dict) and m.get("type")=="result"), {})
print(eval(sys.argv[2], {"json": json}, {"d": d}))' "$@"; }
pending_claude1() { grep -Eq '^## D-[0-9]+ .*pending claude1' docs/DECISIONS.md; }

BUILD_SCHEMA='{"type":"object","properties":{
 "iteration":{"type":"string","description":"NN, two digits"},
 "cycle":{"type":"integer"},
 "status":{"type":"string","enum":["built","blocked"],"description":"blocked = you stopped with questions, a denied command, a conflict between sources, or anything Chris must resolve"},
 "branch":{"type":"string"},
 "blocker":{"type":"string","description":"empty when built"}},
 "required":["iteration","cycle","status","branch","blocker"]}'
REVIEW_SCHEMA='{"type":"object","properties":{
 "iteration":{"type":"string"},
 "cycle":{"type":"integer"},
 "verdict":{"type":"string","enum":["Accept","Fix","Rethink"]},
 "checkpoint_due":{"type":"boolean"},
 "needs_chris":{"type":"boolean","description":"see REVIEWER.md, Loop status"},
 "needs_chris_reasons":{"type":"array","items":{"type":"string"}},
 "next_hw":{"type":"string","enum":["none","safe-read","beyond-safe-read"],"description":"class of the hardware section of the NEXT.md you just wrote; see REVIEWER.md, Loop status"}},
 "required":["iteration","cycle","verdict","checkpoint_due","needs_chris","needs_chris_reasons","next_hw"]}'

# Effort: pass --effort only if this CLI has it; otherwise the CLI default applies (logged).
EFFORT_FLAG=0; claude --help 2>/dev/null | grep -q -- '--effort' && EFFORT_FLAG=1
next_effort() { grep -m1 -i 'Recommended model/effort' docs/NEXT.md | grep -o -i -E 'low|medium|high|xhigh|max' | head -1 | tr 'A-Z' 'a-z'; }

run_claude() {  # $1=label $2=model $3=effort $4=schema $5=prompt
  local out="$WORK/$1.json" args=(-p "$5" --model "$2" --settings "$SETTINGS"
        --permission-mode acceptEdits --permission-prompts none
        --output-format json --json-schema "$4")
  [ "$EFFORT_FLAG" = 1 ] && [ -n "$3" ] && args+=(--effort "$3")
  say "run $1: model=$2 effort requested=${3:-none}$([ "$EFFORT_FLAG" = 1 ] || echo ' (CLI has no --effort flag: CLI default used)')"
  claude "${args[@]}" > "$out" 2> "$WORK/$1.stderr"
  local rc=$?
  [ $rc -ne 0 ] && finish "$1 exited $rc (see $WORK/$1.stderr)"
  [ "$(json_field "$out" 'd.get("is_error", False)')" = "True" ] && finish "$1 reported an error"
  say "$1 cost (estimate, USD): $(json_field "$out" 'd.get("total_cost_usd")'); turns $(json_field "$out" 'd.get("num_turns")'); permission denials: $(json_field "$out" 'len(d.get("permission_denials") or [])')"
  json_field "$out" 'json.dumps(d["structured_output"])' > "$WORK/$1.status.json" 2>/dev/null \
    || finish "$1 returned no structured output"
}
s() { json_field "$WORK/$1.status.json" "d[\"$2\"]"; }

# ---- preflight ----
say "loop start $STAMP; claude $(claude --version 2>/dev/null); max accepts $MAX_ACCEPTS"
[ -f "$SETTINGS" ] || { echo "missing $SETTINGS"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "check out main first"; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean"; exit 1; }
git fetch -q origin && [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "main is not in sync with origin/main"; exit 1; }
pending_claude1 && { echo "a DECISIONS entry is pending claude1"; exit 1; }
grep -q '^No task' docs/NEXT.md && { echo "NEXT.md has no task"; exit 1; }

accepts=0; fixes=0
while :; do
  if [ -n "${RESUME_REVIEW:-}" ]; then
    # ---- resume: the build already exists on this branch ----
    BR="$RESUME_REVIEW"; NN="${BR#iter/}"; RESUME_REVIEW=""
    git rev-parse -q --verify "refs/heads/$BR" >/dev/null || finish "RESUME_REVIEW branch $BR not found"
    git push -q -u origin "$BR" || finish "push of $BR failed"
    say "resuming: review of existing build on $BR (pushed)"
  else
    # ---- build ----
    run_claude "b$accepts-$fixes-build" "$BUILDER_MODEL" "$(next_effort)" "$BUILD_SCHEMA" "/build"
    B="b$accepts-$fixes-build"
    [ "$(s $B status)" = built ] || finish "builder blocked: $(s $B blocker)"
    NN="$(s $B iteration)"; BR="$(s $B branch)"
    [ -z "$(git status --porcelain)" ] || finish "builder left the tree dirty"
    [ "$(git rev-parse --abbrev-ref HEAD)" = "$BR" ] || finish "builder ended on $(git rev-parse --abbrev-ref HEAD), reported $BR"
    git push -q -u origin "$BR" || finish "push of $BR failed"
    say "iteration $NN cycle $(s $B cycle) built and pushed ($BR)"
  fi

  # ---- review ----
  R="b$accepts-$fixes-review"
  run_claude "$R" "$REVIEWER_MODEL" "high" "$REVIEW_SCHEMA" "/review"
  V="$(s $R verdict)"
  [ -z "$(git status --porcelain)" ] || finish "reviewer left the tree dirty"
  say "iteration $NN review: $V"
  case "$V" in
    Accept)
      [ "$(git rev-parse --abbrev-ref HEAD)" = main ] || finish "Accept but reviewer not on main"
      git rev-parse -q --verify "refs/tags/iter-$NN" >/dev/null || finish "Accept but tag iter-$NN missing"
      git push -q origin main --tags || finish "push of main/tags failed"
      accepts=$((accepts+1)); fixes=0 ;;
    Fix)
      git push -q origin "$BR" || finish "push of $BR failed"
      fixes=$((fixes+1))
      [ $fixes -ge 2 ] && finish "second consecutive Fix on iteration $NN (checkpoint due)" ;;
    *) finish "Rethink on iteration $NN" ;;
  esac

  # ---- gates ----
  [ "$(s $R checkpoint_due)" = True ] && finish "checkpoint due after iteration $NN"
  [ "$(s $R needs_chris)" = True ] && finish "reviewer needs Chris: $(json_field "$WORK/$R.status.json" '"; ".join(d["needs_chris_reasons"])')"
  [ "$(s $R next_hw)" = beyond-safe-read ] && finish "next NEXT.md has hardware beyond safe-read; Chris/claude1 must approve"
  pending_claude1 && finish "a DECISIONS entry is pending claude1"
  [ $accepts -ge "$MAX_ACCEPTS" ] && finish "reached $MAX_ACCEPTS accepted iterations"
done
