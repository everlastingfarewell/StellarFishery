# TRIMUI Brick port (A133P / PowerVR GE8300 / Tina Linux)

Status: **toolchain deployed, rendering blocked by the GPU driver.**

The device runs Tina Linux (kernel 4.9.191, glibc 2.33) on an Allwinner A133P
with a PowerVR GE8300. It has no Python and no usable `opkg` feed, but it is
reachable over ADB: `adb devices` shows a `TRIMUI ADB` device with a root shell.
SSH does not work over the local Wi-Fi because the access point isolates
clients; neither side can ping the other.

## Deploy

```
tools/deploy-brick.sh            # bundle, push to /opt/stellar, run the probe
tools/deploy-brick.sh --rebuild  # refetch the runtime and wheels first
```

What the bundle contains: a python-build-standalone CPython 3.13 for
aarch64-unknown-linux-gnu (its oldest required glibc symbol is 2.18, the device
has 2.33) and the aarch64 wheels, installed on the host with

```
uv pip install --python-version 3.13 --python-platform aarch64-unknown-linux-gnu \
    --only-binary :all: --target vendor -r requirements.txt
```

`/mnt/UDISK` is FAT, so everything is extracted to `/opt/stellar`, the writable
ext4 overlay. Run the probe on the device with:

```
cd /opt/stellar && PYTHONPATH=$PWD/vendor ./python/bin/python3 tools/brick_probe.py
```

The probe writes `data/platform.npy`, the capability file `stellar.platform`
reads. Deleting it restores the full-capability defaults.
It must run with `WGPU_BACKEND_TYPE=Vulkan` in the environment (`water.py` /
`stellar.platform.request_device` sets it at import time, so running from the
shell needs it too).

## Verified on the device

- Python 3.13.18, numpy, Pillow and wgpu 0.33.0 import and run.
- wgpu finds `PowerVR Rogue GE8300` through Vulkan:
  `backend_type='Vulkan'`, driver `1.19@6345021`, `max-texture-dimension-2d`
  4096, `texture-adapter-specific-format-features` supported,
  `max-storage-textures-per-shader-stage` 8.
- Storage textures (`r32float`, `rg32float`), shader module creation and
  compute pipelines are created without validation errors.

## Blocking issues

1. **Reading GPU results crashes.** The first host read - `map_sync`,
   `copy_texture_to_buffer`, or `read_texture` - aborts the process (SIGSEGV
   inside wgpu-native / `libVK_IMG.so`). A `clear_buffer` followed by
   `map_sync` crashes too, so it is not shader-related; waiting with
   `on_submitted_work_done_sync` first does not help, and the GL backend panics
   during adapter enumeration (`glGetString but it was not loaded`). The height
   field, picking, buoyancy probes and both acceptance suites all need readback.
2. **No shader compiler on the device.** glslc is absent, and its GLSL
   frontend cannot read WGSL either, so `tools/build-spv.py` (needs naga) must
   run on the host and ship `spv/`. The height field ships as
   `data/water.spv` and `stellar.simulation.shader_binary` reads it when glslc
   is missing.
3. **No window system.** `examples/demo.py` opens a GLFW window through
   rendercanvas, which needs X or Wayland. Showing frames on the 1024x768 fbdev
   needs an offscreen canvas writing `/dev/fb0` plus evdev input, and still
   depends on 1.

`stellar.platform` maps these to capabilities: `wgsl` (compiler present),
`spirv` (prebuilt bytecode usable) and `readback`. `stellar.renderer` skips the
`sea.probe` pipeline and falls back to `Water.pick` on the host height field
when `readback` is false.

## Next steps

- Try Mesa's software Vulkan driver (lavapipe / `vulkan-swrast`) on the device
  to see whether readback works without the PowerVR driver.
- Or rebuild wgpu-native against the device's toolchain, or try an older
  wgpu-py, to find a version whose GL path initialises on this libmali/PowerVR
  stack.
- Or keep the Brick as a compute-only target: push the fixed-step kernel and
  visualise the height field on the host from recorded captures.
