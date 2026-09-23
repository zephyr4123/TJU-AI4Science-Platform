#!/usr/bin/env bash
# package.sh X.Y.Z —— 出包：dist/ai4sci-<ver>-py3-none-any.whl + sdist + 各自的 .sha256。
# 包里带页面与出厂件：先构建页面，把 workflows / templates / domains / skills / coordinator / 页面拷进
# framework/shipped/（不进 git，paths.py 在包模式下从这里读），再 uv build。版本号由 setuptools-scm 从 tag 读，
# 与传进来的 X.Y.Z 对账：不是 tag 上出的包名字带 .dev，只当快照。
set -euo pipefail

die() { echo "package: $*" >&2; exit 1; }

VER="${1:-}"
[ -n "$VER" ] || die "用法：make package VERSION=X.Y.Z"
VER="${VER#v}"

cd "$(git rev-parse --show-toplevel)"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
[ -x "$UV" ] || die "缺 uv：curl -LsSf https://astral.sh/uv/install.sh | sh"

make ui
rm -rf framework/shipped dist
mkdir -p framework/shipped
for d in workflows templates domains skills coordinator; do
  cp -R "$d" "framework/shipped/$d"
done
cp -R ui/web/dist framework/shipped/ui
# 出厂件里的运行产物不带走：skill 脚本的 venv、样例的 __pycache__
find framework/shipped -name "__pycache__" -type d -prune -exec rm -rf {} +
find framework/shipped -name ".venv" -type d -prune -exec rm -rf {} +

"$UV" build
rm -rf framework/shipped

built="$(ls dist/ai4sci-*.whl)"
case "$built" in
  *"ai4sci-$VER-"*) ;;
  *) echo "package: 出的是 $(basename "$built")，不是 $VER 的正式包（HEAD 不在 v$VER 这个 tag 上，当快照）" >&2 ;;
esac
( cd dist && for f in *.whl *.tar.gz; do shasum -a 256 "$f" > "$f.sha256"; done )
ls -1 dist
