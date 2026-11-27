# TrimUI Brick Pro (TG4040)

From the repository root on a computer with NumPy and Pillow installed, preview the handheld ocean at a fixed simulation time:

```sh
python -m stellar.handheld --preview brick-preview.png --time 1.5
```

The PNG uses the handheld renderer's 192 × 144 image and the same nearest-neighbor scaling as the device. Omit `--time` for the initial frame.

Run `bash tools/deploy-brick.sh` with the device connected over ADB. The installer reuses the Python, NumPy and Pillow deployment under `/opt/stellar` when available. A fresh installation also needs curl, tar, uv and internet access on the host. The stock firmware tested was Tina Linux 4.9.191, version 1.1.2.

Start the demo with `adb shell /mnt/UDISK/Apps/StellarFishery/launch.sh`. The launcher runs continuously by default. Pass `--frames 60` for a bounded run. The original entry point also works with `adb shell 'cd /opt/stellar && ./python/bin/python3 demo.py'`. The installer replaces that entry point in place.

The handheld renderer uses the same three directional JONSWAP seed bands as the desktop renderer. NumPy evolves the Fourier modes and transforms surface slopes on the CPU. A 192 × 144 perspective view shades deep water, the sand bank and wave highlights. Pillow scales the image to the 1024 × 768 screen and the launcher writes it to the active framebuffer offset. The code exits on joystick button events numbered 6 or 7. Their physical mapping still needs verification. Mouse clicks have no action.

This handheld mode omits the desktop impact solver, buoyancy queries, clipmap geometry and persistent foam. The desktop Vulkan renderer and acceptance suite continue to use GPU readback. On the tested PowerVR stack, readback crashed even after clearing a buffer. The handheld path runs without Vulkan, shader compilation or a desktop window system.

The left analog stick moves the camera on the horizontal plane. The camera starts four metres above the ocean. Hold R1 to rise or L1 to descend at 3 metres per second, with no upper or lower height limit, allowing travel below the ocean plane. Holding both keeps the height steady. Push up/down to move forward/backward along the viewing heading, and left/right to strafe. The right stick turns the view left/right (yaw) and up/down (pitch). Full stick movement travels at 6 metres per second. Yaw turns at 1.4 radians per second and pitch at 1 radian per second, with pitch limited to ±1.2 radians relative to the initial view. A 15% dead zone suppresses drift, and diagonal movement is limited to the same maximum speed.

The launcher reads Linux's joystick axis map, using ABS_X/ABS_Y for the left stick and ABS_RX/ABS_RY or ABS_Z/ABS_RZ for the right stick. It prints the selected event indices at startup. Initialization events establish the current stick positions and shoulder-button states. Height controls use Linux BTN_TL/BTN_TR codes. On the connected TG4040 these resolve to event indices 4/5. Hardware axis mapping, direction, and performance with camera movement still require verification on the TG4040. Local regression checks run with `python -m unittest tests.test_handheld`.

On the connected TG4040 the release rendered 60 frames in 5.88 seconds. Internal user storage at `/mnt/UDISK` was mounted as ext4.
