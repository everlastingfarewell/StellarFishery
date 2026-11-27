# Open water, optics and foam

Use the installation steps in [milestone1.md](milestone1.md), then run `python -m examples.demo` (or `./run.sh`).
The demo starts in low wind. Press **1** for zero background energy or **2** for low wind. **G** toggles a 320 m analytical swell in wind. Hold **Q/E** to rotate the sun. Right-drag orbits, middle-drag zooms, WASD moves, and left press/release creates a local impact.

## Milestone 2

The default directional JONSWAP sea uses 3.5 m/s wind, heading 0.7 radians, 12 km fetch and a fourth-power cosine spreading function. Spectrum.configure accepts each parameter. Seed 1729 reproduces the same realization. The three periodic domains span 256, 32 and 4 m. Smooth complementary weights partition spectral variance between overlapping bands. Two workgroup FFT passes evolve Hermitian pairs and reconstruct displacement, slope and horizontal orbital velocity at each simulation tick.

Eight stitched square clipmap levels extend 512 m along each axis from the interaction region center. World-coordinate sampling anchors the waves. Band attenuation near each resolution limit transfers short-wave detail to roughness. The local impact field fades into the ocean at its border. The renderer exposes pick and sample queries on the same displaced triangles used for drawing.

## Milestone 3

An opaque pass draws a sand bank and four stones to scene color and linear depth. Water traces reflection and refraction against these buffers. Screen-edge and distance confidence blend the reflection into a roughness-filtered analytic sky. Underwater distance controls RGB Beer–Lambert transmission. Crest lighting uses elevation, surface normal and the shared solar direction.

Within the moving 16 m interaction patch, foam accumulates from compression of horizontal displacement and shallow-water wave arrivals. A fixed-step ping-pong pass backtraces through orbital velocity and local contact flow, decays old coverage, and clears exposed cells on scroll. Outside the patch the renderer draws spectral water without persistent foam.

## Verification

Run `python -m tests.test_ocean_acceptance` on a Vulkan device. It checks evolved height, both displacement components and slopes against NumPy, tests clipmap edge ownership, samples a crest before and after scrolling, compares the same local impact in both presets, measures offshore foam decay, and resizes the renderer. The full suite passed on AMD Radeon 780M Graphics. The offshore stress shot peaked at full coverage at 0.67 s and fell to 0.00931 at 6.67 s.

The [reference recordings](../captures/ocean) include a frozen-time camera traverse, matched impact replays, a rock reflection pan, backlit swell, shallow/deep stones, and an advected whitecap. The frozen-time traverse isolates camera-induced motion. The whitecap shot uses two opposing horizontal impulses to make advection and decay repeatable.
