#!/usr/bin/env bash
# Open the PR on GitHub.
#
# Usage:
#   ./scripts/open_pr.sh                       # push branch + open PR on the configured fork
#   ./scripts/open_pr.sh --dry-run             # just print the commands
#   UPSTREAM=ahujasid/blender-mcp ./scripts/open_pr.sh
#                                              # target a different upstream
#
# Requirements: gh CLI authenticated, branch already prepared.
#
set -euo pipefail

BRANCH="pr/transport-hardening-blender-compat"
UPSTREAM="${UPSTREAM:-yuri-schmaltz/mcp-blender}"
HEAD="$(git rev-parse --abbrev-ref HEAD)"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n  $ %s\n' "$*"
  else
    eval "$@"
  fi
}

if [ "$HEAD" != "$BRANCH" ]; then
  echo "refusing to push from $HEAD; checkout $BRANCH first" >&2
  exit 1
fi

# Sanity check: main must be at the upstream tip, so the diff is clean.
MAIN_TIP="$(git rev-parse main)"
UPSTREAM_TIP="$(git ls-remote https://github.com/yuri-schmaltz/mcp-blender.git HEAD | cut -f1)"
if [ "$MAIN_TIP" != "$UPSTREAM_TIP" ]; then
  echo "warning: local main ($MAIN_TIP) differs from origin main ($UPSTREAM_TIP)" >&2
  echo "         consider 'git reset --hard $UPSTREAM_TIP' on main before opening the PR" >&2
fi

run "git push -u origin $BRANCH"

# Build the PR body from PR_BODY.md
if [ -f PR_BODY.md ]; then
  PR_BODY_FILE="PR_BODY.md"
else
  echo "PR_BODY.md missing -- aborting" >&2
  exit 1
fi

run "gh pr create \\
  --base main \\
  --head $BRANCH \\
  --repo $UPSTREAM \\
  --title 'Transport hardening + Blender 4.x compatibility' \\
  --body-file $PR_BODY_FILE \\
  --label 'enhancement,security' \\
  --reviewer ahujasid"

echo
echo "Done. Visit: https://github.com/$UPSTREAM/pull/$(gh pr view --json number --jq .number 2>/dev/null || echo NEW)"
