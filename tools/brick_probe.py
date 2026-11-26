"""Probe the TRIMUI Brick: adapter, capabilities, and the shader modules.

Runs on the device with the bundled aarch64 CPython:

    cd /opt/stellar && PYTHONPATH=$PWD/vendor ./python/bin/python3 tools/brick_probe.py

The readback check is last because the first host read of GPU data aborts the
process on this driver.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import traceback

os.environ.setdefault("WGPU_BACKEND_TYPE", "Vulkan")


def main():
    import wgpu

    from stellar import brick
    from stellar.platform import (CAPABILITIES, request_device,
                                  write_platform_profile)

    print("wgpu", wgpu.__version__)
    adapter, device = request_device()
    info = adapter.info
    print("adapter:", info["device"], "|", info["description"])
    print("backend:", info["backend_type"], "| type:", info["adapter_type"])
    print("limits:", {k: adapter.limits[k] for k in (
        "max-texture-dimension-2d", "max-compute-workgroup-size-x",
        "max-storage-textures-per-shader-stage")})

    print("readback is checked last; a crash here means no host readback")
    capabilities = brick.detect(device)
    profile = write_platform_profile(info["device"], **capabilities)
    print("capabilities:", {name: profile[name] for name in CAPABILITIES})
    print("written to data/platform.npy")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
