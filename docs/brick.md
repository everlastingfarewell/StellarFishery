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

The left analog stick moves the camera on the horizontal plane. The camera starts 0.8 metres above sea level. Hold R1 to rise or L1 to descend at 4.5 metres per second, bounded by 1.6 metres of vertical seabed clearance and a maximum height of 0.8 metres above sea level in sufficiently deep water (terrain clearance takes priority near shore). Holding both keeps the height steady. Push up/down to move forward/backward along the viewing heading, and left/right to strafe. The right stick turns the view left/right (yaw) and up/down (pitch). Full stick movement travels at 9 metres per second. Yaw turns at 1.4 radians per second and pitch at 1 radian per second, with pitch limited to ±1.2 radians relative to the initial view. A 15% dead zone suppresses drift, and diagonal movement is limited to the same maximum speed.

The launcher reads Linux's joystick axis map, using ABS_X/ABS_Y for the left stick and ABS_RX/ABS_RY or ABS_Z/ABS_RZ for the right stick. It prints the selected event indices at startup. Initialization events establish the current stick positions and shoulder-button states. Height controls use Linux BTN_TL/BTN_TR codes. On the connected TG4040 these resolve to event indices 4/5. Hardware axis mapping, direction, and performance with camera movement still require verification on the TG4040. Local regression checks run with `python -m unittest tests.test_handheld`.

On the connected TG4040 the release rendered 60 frames in 5.88 seconds. Internal user storage at `/mnt/UDISK` was mounted as ext4.

When camera height is negative, the handheld renderer switches to an underwater view with blue-green absorption tint, scrolling caustics on a curved seabed that deepens offshore, and linear distance fog. Camera depth controls a uniform tint and fog color. Caustic contrast fades linearly with seabed depth from 2 to 16 metres and with viewing distance from 2.8 to 18.2 metres. At either far limit it disappears completely and texture reads stop. A repeatable random polygon shoreline around x = -6 metres joins the coarse sandy beach to the sea. Each beach face inclines at 10 degrees and each seabed face at 15 degrees. Beach elevation levels off into a plateau at 4 metres above sea level. Faces join at bends spaced 24 metres alongshore. Horizontal movement can cross the shoreline freely. Where terrain clearance requires more than 0.8 metres above sea level, the camera follows the terrain at 1.6 metres above it. Returning to deeper water restores the 0.8-metre sea-level cap. Camera movement and initial placement enforce terrain clearance. Looking upward shows a flat tinted water ceiling.

Underwater frames skip all surface FFTs and wave shading. Above-water frames skip underwater shading. Crossing back above zero resumes the surface at the current simulation time. The underwater view uses the same 192 × 144 image, nearest-neighbor upscale, and single opaque framebuffer write as the surface view.

The CPU framebuffer backend uses no GPU shader passes. Its underwater effect performs one nearest lookup into the pre-baked 128 × 128 grayscale `stellar/caustics.png` per visible seabed pixel, with zero detail-map samples. Color, fog, and wrapped UV calculations use NumPy float16; world projection uses float32. Linear fog is mixed directly into the final RGB image. The runtime uses no underwater exponential absorption, procedural caustics, refraction, depth buffers, framebuffer sampling, blending, or wave evaluation. The tile occupies 16 KiB decoded and loads once on first entering water. The offline authoring command `python tools/bake-caustics.py` reproduces the periodic tile. Deployment and Python package data include the PNG.

Preview the effect with `python -m stellar.handheld --preview underwater.png --height -2 --time 3`, or animate it with `python -m stellar.handheld --window --height -2`. On the device, `/usr/trimui/apps/DEMO/DEMO --height -2 --frames 60` starts a bounded underwater run. Physical display appearance requires user review.

The revised terrain preview passed 13 tests on TG4040. Publication to the authentication feature branch awaits user approval.
