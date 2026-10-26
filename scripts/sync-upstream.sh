#!/usr/bin/env bash
# Merge upstream (ChrisDKN/Amethyst-Mod-Manager) into the current branch.
#
# Paths listed in scripts/removed-upstream-paths.txt are deleted again after
# the merge, which resolves the modify/delete conflicts upstream edits to
# them would otherwise cause. Any other conflict is left for you to resolve;
# the merge is not committed until there are none.
#
# Usage: scripts/sync-upstream.sh [upstream-ref]   (default: upstream/main)

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
REF="${1:-upstream/main}"
LIST="scripts/removed-upstream-paths.txt"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "error: the working tree has uncommitted changes" >&2
    exit 1
fi

git fetch upstream
git merge --no-ff --no-commit "$REF" || true

# `git rm` also resolves a modify/delete conflict as "deleted".
grep -v '^#' "$LIST" | grep -v '^$' | tr '\n' '\0' |
    xargs -0 git rm -r -q -f --ignore-unmatch -- >/dev/null

CONFLICTS="$(git diff --name-only --diff-filter=U)"
if [ -n "$CONFLICTS" ]; then
    echo "Resolve these conflicts, then run 'git commit':"
    echo "$CONFLICTS" | sed 's/^/  /'
    exit 1
fi

if git diff --cached --quiet && [ ! -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]; then
    echo "Already up to date with $REF."
    exit 0
fi
git commit -q --no-edit
echo "Merged $REF: $(git log -1 --format='%h %s')"
