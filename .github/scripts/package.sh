#!/usr/bin/env bash
# package.sh X.Y.Z —— 出包：dist/<name>-<ver>.tar.gz + .sha256。
# 技术栈未定，目前的「包」是 tag 对应的源码快照（git archive，遵守 .gitattributes 的 export-ignore）。
# 定栈以后，真正的构建接在这里（或在 Makefile 的 package 目标里前置一步 build），流水线不用改。
set -euo pipefail

die() { echo "package: $*" >&2; exit 1; }

NAME="tju-ai4science-platform"
VER="${1:-}"
[ -n "$VER" ] || die "用法：make package VERSION=X.Y.Z"
VER="${VER#v}"

cd "$(git rev-parse --show-toplevel)"
REF="v$VER"
if ! git rev-parse -q --verify "refs/tags/$REF" >/dev/null; then
  echo "package: tag $REF 不存在，用当前 HEAD 打快照包（非正式版本）" >&2
  REF="HEAD"
fi

mkdir -p dist
OUT="$NAME-$VER.tar.gz"
git archive --format=tar.gz --prefix="$NAME-$VER/" -o "dist/$OUT" "$REF"
( cd dist && shasum -a 256 "$OUT" > "$OUT.sha256" )
echo "✓ dist/$OUT"
cat "dist/$OUT.sha256"
