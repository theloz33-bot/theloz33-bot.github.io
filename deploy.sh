#!/usr/bin/env bash
# Build, audit, commit and push the hub. GitHub Pages serves main → repository root,
# so the generated pages sit next to src/ and the sources stay in src/.
#   ./deploy.sh "Update the hub"
set -euo pipefail
cd "$(dirname "$0")"

if [ -d ../blog-omong-kr ] && [ -d ../blog-omong-studio ]; then
  python3 src/build.py --sync
fi
python3 src/build.py --check
python3 src/tools/audit.py

git add -A
if git diff --cached --quiet; then
  echo "nothing to commit — the site is already up to date"
  exit 0
fi
git commit -m "${1:-Update the hub}"
git push -u origin main
echo "pushed. Pages deploys in about a minute: https://theloz33-bot.github.io/"
