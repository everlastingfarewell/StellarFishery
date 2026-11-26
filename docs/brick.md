# TrimUI Brick Pro (TG4040)

Run `bash tools/deploy-brick.sh` with the device connected over ADB. The installer reuses the Python, NumPy and Pillow deployment under `/opt/stellar` when available. A fresh installation also needs curl, tar, uv and internet access on the host. The stock firmware tested was Tina Linux 4.9.191, version 1.1.2.

Start the demo with `adb shell /mnt/UDISK/Apps/StellarFishery/launch.sh`. The launcher runs continuously by default. Pass `--frames 60` for a bounded run. The original entry point also works with `adb shell 'cd /opt/stellar && ./python/bin/python3 demo.py'`. The installer replaces that entry point in place.

The handheld renderer uses the same three directional JONSWAP seed bands as the desktop renderer. NumPy evolves the Fourier modes and transforms surface slopes on the CPU. A 192 × 144 perspective view shades deep water, the sand bank and wave highlights. Pillow scales the image to the 1024 × 768 screen and the launcher writes it to the active framebuffer offset. Joystick buttons 6 and 7 exit. Mouse clicks have no action.

This handheld mode omits the desktop impact solver, buoyancy queries, clipmap geometry and persistent foam. The desktop Vulkan renderer and acceptance suite continue to use GPU readback. On the tested PowerVR stack, readback crashed even after clearing a buffer. The handheld path runs without Vulkan, shader compilation or a desktop window system.

On the connected TG4040 the release rendered 60 frames in 5.88 seconds. Internal user storage at `/mnt/UDISK` was mounted as ext4.
