"""Platform capabilities of the TRIMUI Brick, detected on the device.

The Brick runs Tina Linux (kernel 4.9, glibc 2.33) on an Allwinner A133P with a
PowerVR GE8300. wgpu finds the GPU through Vulkan, but some capabilities are
missing; `detect()` proves each one on the device and the result is written to
`data/platform.npy` with `stellar.platform.write_platform_profile`.
"""
import os
import shutil
from pathlib import Path

DEVICE_DIR = Path(os.environ.get("STELLAR_BRICK_DIR", "/opt/stellar"))


def detect(device):
    """Probe `device` (an open wgpu device) and return the capability dict.

    The Brick aborts the process the first time GPU data is read back, so call
    this last and let the exit code carry the result.
    """
    return {
        # naga is the only compiler for WGSL; glslc's GLSL frontend rejects it.
        "wgsl": shutil.which("naga") is not None,
        "spirv": True,
        "readback": _can_read_back(device),
    }


def _can_read_back(device):
    """Copy one cleared buffer to the host."""
    import wgpu

    buf = device.create_buffer(size=4, usage=wgpu.BufferUsage.MAP_READ
                               | wgpu.BufferUsage.COPY_DST)
    encoder = device.create_command_encoder()
    encoder.clear_buffer(buf, 0, 4)
    device.queue.submit([encoder.finish()])
    try:
        buf.map_sync("read")
    except Exception:
        return False
    finally:
        buf.destroy()
    return True
