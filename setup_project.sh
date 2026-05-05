#!/usr/bin/env sh
set -e
git checkout -b develop || git checkout develop
git push -u origin develop
mkdir -p worktree/main
cd worktree
git worktree add main main
cd ..
weave setup

cd my-ebook
ln -s AGENTS-PROGRAMMING.md AGENTS.md
