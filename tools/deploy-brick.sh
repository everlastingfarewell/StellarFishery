#!/usr/bin/env bash
# Deploy StellarFishery to the TRIMUI Brick (A133P / PowerVR GE8300 / Tina Linux)
# over ADB. The device has no X/Wayland and no Python, so we ship a
# python-build-standalone runtime plus aarch64 wheels and run offscreen.
#
#   tools/deploy-brick.sh           # reuse the prepared bundle, push and run
#   tools/deploy-brick.sh --rebuild # rebuild runtime, wheels and bundle
#
# The device must show up in `adb devices`. Everything lands in /opt/stellar,
# which is the writable ext4 overlay partition.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
cache="$root/.cache/brick"
bundle="$cache/stellar-brick.tar.gz"
remote=/opt/stellar
py_version=3.13
pbs_tag=20261124
pbs_file="cpython-3.13.18+${pbs_tag}-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz"
pbs_mirror="https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone/${pbs_tag}"
pbs_fallback="https://gh-proxy.com/https://github.com/astral-sh/python-build-standalone/releases/download/${pbs_tag}"

rebuild=false
[ "${1:-}" = "--rebuild" ] && rebuild=true

mkdir -p "$cache"

if $rebuild || [ ! -x "$cache/python/bin/python3.13" ]; then
    echo "== fetching aarch64 CPython $py_version"
    rm -rf "$cache/python" "$cache/cpython-aarch64.tar.gz"
    # The '+' has to be percent encoded for both mirrors.
    name_esc=${pbs_file//+/%2B}
    curl -fsSL --http1.1 --retry 5 --retry-all-errors -m 900 \
        -o "$cache/cpython-aarch64.tar.gz" "$pbs_mirror/$name_esc" \
        || curl -fsSL --http1.1 --retry 5 --retry-all-errors -m 900 \
        -o "$cache/cpython-aarch64.tar.gz" "$pbs_fallback/$name_esc"
    tar xzf "$cache/cpython-aarch64.tar.gz" -C "$cache"
fi

if $rebuild || [ ! -d "$cache/vendor/wgpu" ]; then
    echo "== fetching aarch64 wheels (cp$py_version)"
    rm -rf "$cache/vendor"
    UV_CACHE_DIR="$root/.cache/uv" uv pip install \
        --python-version "$py_version" --python-platform aarch64-unknown-linux-gnu \
        --only-binary :all: --target "$cache/vendor" -r requirements.txt
fi

# Shader bytecode. None of these can be compiled on the device: no glslc, and
# glslc's GLSL frontend cannot read WGSL, so the .wgsl modules still need a
# WGSL -> SPIR-V compiler (naga). Those are stubbed on the device.
echo "== building SPIR-V"
python3 tools/build-spv.py --out spv              # WGSL, vulkan1.1
glslangValidator -V -S comp --target-env vulkan1.1 shaders/wave.comp \
    -o data/water.spv
spirv-val --target-env vulkan1.1 data/water.spv

if $rebuild || [ ! -f "$bundle" ]; then
    echo "== building bundle"
    rm -f "$bundle"
    tar czf "$bundle" -C "$cache" python vendor \
        -C "$root" stellar examples tests tools shaders spv data captures \
        run.sh requirements.txt README.md docs
fi
echo "bundle: $(du -h "$bundle" | cut -f1)"

echo "== waiting for device"
adb wait-for-device
adb shell 'mkdir -p /opt/stellar'

echo "== pushing $(du -h "$bundle" | cut -f1)"
adb push "$bundle" /mnt/UDISK/stellar-brick.tar.gz
adb shell "rm -rf $remote && mkdir -p $remote"
adb shell "tar xzf /mnt/UDISK/stellar-brick.tar.gz -C $remote && rm -f /mnt/UDISK/stellar-brick.tar.gz"
adb shell "ls $remote"

echo "== probing Vulkan on the device"
adb shell "cd $remote && PYTHONPATH=\$PWD/vendor ./python/bin/python3 tools/brick_probe.py"
