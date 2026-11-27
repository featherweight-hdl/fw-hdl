#!/bin/sh
# Fail if the old front end comes back to this branch.
#
# The pre-2026-11 front end (src/, python/fw/hdl and its dfm tasks) is frozen
# on branch `legacy` (tag `legacy-fe-final`).
# Run in CI and usable as a pre-commit hook. Exits 1 on any hit.
cd "$(git rev-parse --show-toplevel)" || exit 2
fail=0

paths=$(git ls-files -- 'src/*' 'python/fw/hdl/*')
if [ -n "$paths" ]; then
    echo "error: legacy front-end paths are tracked:"
    echo "$paths" | head -20
    fail=1
fi

# dfm task namespaces that only the old front end provides.
uses=$(git grep -nE 'uses:[[:space:]]*fw\.hdl\.(api|xls|spl|report|knobs|formal|check|lower|sync)\.' \
       -- '*flow.yaml' '*.dv' 2>/dev/null)
if [ -n "$uses" ]; then
    echo "error: flows use legacy fw.hdl.* dfm tasks:"
    echo "$uses"
    fail=1
fi

[ $fail -eq 0 ] && echo "OK: no legacy front end on this branch"
exit $fail
