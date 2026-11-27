#!/usr/bin/env bash
# Install the Mesa Vulkan driver for Intel GPUs (vulkan-intel) into
# ~/.local/vulkan-intel without root, then tell the loader where it is.
#
# Use this only if you cannot run `sudo pacman -S vulkan-intel`. The version
# downloaded is the one matching the installed `mesa` package, because the
# driver links against the system Mesa libraries.
set -euo pipefail

dest="${VULKAN_ICD_DIR:-$HOME/.local/vulkan-intel}"
archive="https://archive.archlinux.org/packages/v/vulkan-intel"

if ls /usr/share/vulkan/icd.d/*.json >/dev/null 2>&1; then
    echo "A system-wide Vulkan ICD is already installed, nothing to do."
    exit 0
fi

version=$(pacman -Q mesa | awk '{print $2}')
if [ -z "$version" ]; then
    echo "error: cannot read the installed mesa version" >&2
    exit 1
fi

name="vulkan-intel-${version}-x86_64.pkg.tar.zst"
url="$archive/${name//:/%3A}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Downloading $url"
curl -fsSL --http1.1 --retry 3 -o "$tmp/pkg.tar.zst" "$url"
mkdir -p "$tmp/pkg"
bsdtar -xf "$tmp/pkg.tar.zst" -C "$tmp/pkg"

mkdir -p "$dest"
cp "$tmp/pkg/usr/lib/libvulkan_intel.so" "$dest/"
cp "$tmp/pkg/usr/share/licenses/vulkan-intel/license.rst" "$dest/" 2>/dev/null || true
cp "$tmp/pkg/usr/share/vulkan/icd.d/intel_icd.json" "$dest/"
# The manifest must name the driver by absolute path: a bare filename is
# resolved against the loader's search path, not the manifest directory.
python3 - "$dest" <<'PY'
import json, sys
from pathlib import Path
dest = Path(sys.argv[1])
manifest = dest / "intel_icd.json"
data = json.loads(manifest.read_text())
data["ICD"]["library_path"] = str(dest / "libvulkan_intel.so")
manifest.write_text(json.dumps(data, indent=4) + "\n")
PY

echo "Installed to $dest"
echo "Run the demo with:  ./run.sh"
