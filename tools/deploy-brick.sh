#!/usr/bin/env bash
# Install or refresh the stock TG4040 framebuffer demo over ADB.
# Pass --rebuild to refresh the bundled Python runtime and wheels.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
cache="$root/.cache/brick"
remote=/opt/stellar
py_version=3.13
pbs_tag=20261124
pbs_file="cpython-3.13.18+${pbs_tag}-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz"

rebuild=false
[ "${1:-}" = "--rebuild" ] && rebuild=true

adb wait-for-device
model=$(adb shell cat /etc/model | tr -d '\r\n')
[ "$model" = TG4040 ] || { echo "Expected TG4040, found $model" >&2; exit 1; }
adb shell "mkdir -p $remote/stellar /mnt/UDISK/Apps/StellarFishery"
if $rebuild || ! adb shell "cd $remote && PYTHONPATH=$remote/vendor ./python/bin/python3 -c 'import numpy, PIL.Image'"; then
    mkdir -p "$cache/vendor"
    url="https://github.com/astral-sh/python-build-standalone/releases/download/$pbs_tag/${pbs_file//+/%2B}"
    curl -fL --retry 3 "$url" -o "$cache/python.tar.gz"
    uv pip install --python-version "$py_version" --python-platform aarch64-unknown-linux-gnu \
        --only-binary :all: --target "$cache/vendor" 'numpy>=2.1,<3' 'Pillow>=11,<14'
    tar czf "$cache/vendor.tar.gz" -C "$cache" vendor
    for part in python vendor; do
        adb push "$cache/$part.tar.gz" "$remote/$part.tar.gz"
        adb shell "cd $remote && tar xzf $part.tar.gz && rm $part.tar.gz"
    done
fi
for file in __init__.py waves.py handheld.py; do
    adb push "stellar/$file" "$remote/stellar/$file"
done
adb push tools/brick-app/demo.py "$remote/demo.py"
for file in config.json launch.sh; do
    adb push "tools/brick-app/$file" "/mnt/UDISK/Apps/StellarFishery/$file"
done
adb shell 'chmod 755 /mnt/UDISK/Apps/StellarFishery/launch.sh && /mnt/UDISK/Apps/StellarFishery/launch.sh --frames 3'
