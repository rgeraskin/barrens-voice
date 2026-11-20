"""The environment for a git of a test's own repository (a temporary one): without the GIT_* variables of a calling
git. A hook or `git rebase --exec` sets GIT_DIR, GIT_INDEX_FILE and the like, and with them the test's `git init`,
commits, tags and `git config` went to the real repository (20.11.2026: a rebase that ran the tests at every commit
left core.bare = true, a test identity and test tags in barrens-voice's .git)."""
from __future__ import annotations

import os


def own_repository_env(**more: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(more)
    return env
