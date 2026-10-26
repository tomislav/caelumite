#!/usr/bin/env bash
# Merge upstream (ChrisDKN/Amethyst-Mod-Manager) into the current branch.
#
# On main, paths listed in scripts/removed-upstream-paths.txt are deleted
# again after the merge, which resolves the modify/delete conflicts upstream
# edits to them would otherwise cause. On the Resources branch (check it out
# in a worktree and run this script from main's checkout) the default ref is
# upstream/Resources, upstream's workflows and Crowdin config are removed
# instead, and changed plugin code is listed for review - Caelumite runs it.
# Any other conflict is left for you to resolve; the merge is not committed
# until there are none.
#
# Usage: scripts/sync-upstream.sh [upstream-ref]
#        (default: upstream/main, or upstream/Resources on Resources)

set -euo pipefail

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
cd "$(git rev-parse --show-toplevel)"
BRANCH="$(git symbolic-ref --short HEAD)"
if [ "$BRANCH" = "Resources" ]; then
    REF="${1:-upstream/Resources}"
    REMOVED=$':(glob).github/**\ncrowdin.yml'
else
    REF="${1:-upstream/main}"
    REMOVED="$(cat "$SCRIPTS/removed-upstream-paths.txt")"
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "error: the working tree has uncommitted changes" >&2
    exit 1
fi

git fetch upstream
# .gitattributes marks files Caelumite replaces (e.g. the logo) merge=ours.
git config merge.ours.driver true
git merge --no-ff --no-commit "$REF" || true

# `git rm` also resolves a modify/delete conflict as "deleted".
printf '%s\n' "$REMOVED" | grep -v '^#' | grep -v '^$' | tr '\n' '\0' |
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
if [ "$BRANCH" = "Resources" ]; then
    CODE="$(git diff --cached --name-only HEAD -- '*.py')"
    if [ -n "$CODE" ]; then
        echo "Plugin code changed - review it before committing and pushing:"
        echo "$CODE" | sed 's/^/  /'
        echo "Then run 'git commit --no-edit'."
        exit 1
    fi
fi
git commit -q --no-edit
echo "Merged $REF: $(git log -1 --format='%h %s')"
