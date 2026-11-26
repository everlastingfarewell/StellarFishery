#!/bin/sh
# Source this file to make the Vulkan driver visible to wgpu.
#
#   . scripts/env.sh
#   python demo.py
#
# Only needed when the system-wide ICD is missing (no vulkan-intel package):
# this points the Vulkan loader at the user-local copy installed by
# scripts/setup-vulkan-icd.sh.

if [ -z "${VK_DRIVER_FILES:-}" ] && [ -z "${VK_ICD_FILENAMES:-}" ]; then
    if ! ls /usr/share/vulkan/icd.d/*.json >/dev/null 2>&1; then
        icd="$HOME/.local/vulkan-intel/intel_icd.json"
        if [ -f "$icd" ]; then
            VK_DRIVER_FILES="$icd"
            export VK_DRIVER_FILES
        fi
        unset icd
    fi
fi
