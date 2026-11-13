#!/bin/bash
# 在 macOS 上打包：生成 dist/EblanaDeskPet.app 和可分发的 dist/EblanaDeskPet-mac.dmg
set -e
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt pyinstaller

./.venv/bin/pyinstaller --noconfirm --clean EblanaDeskPet.spec

rm -rf dist/dmg
mkdir -p dist/dmg
cp -R dist/EblanaDeskPet.app dist/dmg/
ln -s /Applications dist/dmg/Applications
hdiutil create -volname "死芒桌宠" -srcfolder dist/dmg -ov -format UDZO dist/EblanaDeskPet-mac.dmg
rm -rf dist/dmg

echo "完成：dist/EblanaDeskPet-mac.dmg"
