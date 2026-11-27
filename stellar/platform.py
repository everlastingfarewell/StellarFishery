"""Device selection, shader modules and the platform capabilities file.

wgpu normally compiles WGSL inline, but not every target can: the TRIMUI Brick
only works with prebuilt SPIR-V (docs/brick.md) and has no WGSL compiler at all.
Such a platform describes itself in `data/platform.npy`, and every renderer
module that depends on an unavailable capability reports it instead of failing
deep inside wgpu.
"""
import os

import numpy as np
import wgpu
import wgpu.backends.wgpu_native

from .config import PLATFORM_FILE, SPV

_backend_requested = False

# Capabilities a platform may lack. Each one names the shader modules that
# cannot be built without it.
CAPABILITIES = {
    "wgsl": "compiling WGSL shader modules",
    "spirv": "using prebuilt SPIR-V shader modules",
    "readback": "reading simulation results back to the host",
}


def _requested_backend():
    global _backend_requested
    if not _backend_requested:
        _backend_requested = True
        os.environ.setdefault("WGPU_BACKEND_TYPE", "Vulkan")
    return os.environ["WGPU_BACKEND_TYPE"]


def request_device(required_features=("texture-adapter-specific-format-features",)):
    """Return `(adapter, device)` for the Vulkan adapter wgpu prefers."""
    _requested_backend()
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    if adapter.info["backend_type"] != "Vulkan":
        raise RuntimeError("Vulkan backend required")
    return adapter, adapter.request_device_sync(required_features=list(required_features))


def shader_module(device, name, source, spv=None):
    """Create a WGSL module for `source`, or its prebuilt SPIR-V `spv` file.

    `source` is None when the WGSL text is unavailable (a prebuilt-only
    platform such as the Brick). Raises a clear `RuntimeError` naming the
    missing capability instead of handing wgpu an empty module.
    """
    profile = platform_profile()
    if source is not None and profile["wgsl"]:
        return device.create_shader_module(code=source)
    if spv is not None and profile["spirv"] and spv.is_file():
        return device.create_shader_module(code=spv.read_bytes())
    missing = "wgsl" if source is None else "spirv"
    raise RuntimeError(
        f"cannot build shader module {name!r}: this platform has no "
        f"{CAPABILITIES[missing]} (device: {profile['device']}); prebuilt file "
        f"expected at {spv or SPV / name}")


def platform_profile():
    """Capabilities of the current platform; everything is supported by default."""
    profile = {"device": "unknown", "backend": "unknown", "type": "unknown",
               "description": ""}
    profile.update({name: True for name in CAPABILITIES})
    if PLATFORM_FILE.is_file():
        profile.update(dict(np.load(PLATFORM_FILE, allow_pickle=True).item()))
    return profile


def write_platform_profile(device_name, **capabilities):
    """Record this platform's capabilities. Used by the Brick tooling."""
    profile = platform_profile()
    profile["device"] = device_name
    unknown = set(capabilities) - set(CAPABILITIES)
    if unknown:
        raise ValueError(f"unknown capabilities: {sorted(unknown)}")
    profile.update(capabilities)
    PLATFORM_FILE.parent.mkdir(parents=True, exist_ok=True)
    np.save(PLATFORM_FILE, np.array(profile, dtype=object), allow_pickle=True)
    return profile


def prebuilt(name):
    """Path of the prebuilt SPIR-V for a renderer module."""
    return SPV / name
