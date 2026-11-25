# StellarFishery — Vulkan Water and Interaction Plan

Build a fishing demo on a deep, mostly calm sea. A float should respond to small ripples. A large animal breaking the surface should produce a directional splash, thin sheets of water, and droplets that generate secondary ripples on re-entry. Use the same camera and lighting to judge both extremes. Establish the visual target first, then use GPU timings to decide where to reduce cost.

## Rendering target and engineering scope

Use Three.js Water Pro as the visual benchmark. The supplied reference targets the r181+ WebGPU build and TSL, connects water effects explicitly to PostProcessing, and rebuilds dependent nodes when quality changes recreate textures. In native Vulkan, express those dependencies as render passes, image views, descriptors, and synchronization. On a resize or quality change, recreate affected images, rebind their consumers, and retire old resources after their last GPU use.

The full feature set is engine-scale work. Treat several person-months as a rough scope estimate. Deliver the following milestones in order so that the calm-water demo remains playable while more expensive effects are developed.

## Milestone 1 — A single impact on calm water

1. Implement right-drag orbit, middle-drag zoom, and WASD movement. On left-button press, capture the camera origin and ray. On release, intersect that ray with the simulated surface and apply one impulse. Cap the impulse produced by a long press.
2. Implement a world-anchored local grid in Vulkan compute. Advance a damped 2D wave equation at a fixed time step using two height images. Choose the time step from cell spacing and wave speed. Use an absorbing border. For a moving interaction region, scroll the grid through a ring buffer and clear newly exposed cells.
3. Store contact position, radius, impulse vector, and simulation timestamp in each event. For a sustained contact, integrate force over each simulation step. Consume an instantaneous impact once. Distribute its vertical impulse across contact cells using weights that sum to one, including at patch edges.

       cell mass       = water density × cell area × effective contact thickness
       velocity change = cell weight × vertical impulse / cell mass
       height change due to impulse = time step × velocity change

   A negative vertical impulse initially depresses the surface. Calibrate effective contact thickness against a repeatable impact. Route horizontal momentum into a local flow field or active splash particles so it can transport foam and influence wake direction.
4. Displace the mesh and derive normals from the resulting surface. Use one simulation timestamp and surface definition for shading, picking, and buoyancy.

**Acceptance.** From a fixed camera, record a single impact and a repeated burst at two render frame rates. Compare the initial depression, ring radius over time, amplitude decay, and reflections from the patch edge. Check that a frame containing several simulation steps consumes each event exactly once.

## Milestone 2 — Extend the patch to open water

Generate a directional JONSWAP spectrum from wind speed, wind direction, fetch, and directional spread. Evolve phases with deep-water dispersion and preserve conjugate symmetry. Run horizontal and vertical inverse FFT passes on the GPU to produce height, horizontal displacement, and slopes.

Split spectral energy across three overlapping cascades for swell, mid-scale waves, and near-field detail. Partition energy in the overlap bands so their sum preserves the intended spectrum. Add analytical Gerstner swell outside the simulated bands when a shot needs longer wavelengths. Provide low-wind and zero-background-energy presets.

Sample displacement in world coordinates on camera-centered clipmap rings. Match ring boundaries, fade displacement between levels, and transfer unresolved short-wave detail to material roughness. A compute-generated grid with cubic vertex spacing is an alternative geometry layout if profiling identifies a need to concentrate vertices around the boat. Add local disturbance height to the background and derive normals from the combined surface.

**Acceptance.** Move the camera across cascade and clipmap boundaries. Track a crest against a fixed world landmark and inspect the horizon for cracks or shimmer. Repeat the same small impact in the calm and low-wind presets.

## Milestone 3 — Water optics and persistent foam

| Effect | Implementation | Visual check |
|---|---|---|
| Reflection | Render opaque color and depth first. Trace screen-space reflections (SSR) and blend low-confidence hits into a prefiltered sky. Use Fresnel weighting for reflection and transmission. Planar reflection is an option for a prominent shoreline or boat. Hardware ray tracing is an optional later path. | Pan past a reflected object at a grazing angle and inspect the transition as it leaves the screen. |
| Refraction and absorption | Offset scene sampling along the refracted direction, reject invalid foreground samples, and estimate the underwater optical path length L. Apply Beer–Lambert transmission per color channel using exp(−σₐ L). | View the same submerged object in shallow and deep water, including near an occlusion edge. |
| Crest lighting | Approximate subsurface scattering from crest thickness, view direction, and backlighting. Share the sun direction with the sky and specular highlight. | Rotate the light behind a crest and inspect its thin edge. |
| Foam | Compute the Jacobian determinant of the horizontal displacement map. Inject foam into a persistent world-space field where compression approaches folding. Advect with horizontal flow and decay over time. Generate shore foam from water depth and arriving waves. | Follow a whitecap after its crest passes. Inspect the shoreline and the low foam coverage in calm, deep water. |

## Milestone 4 — Animal impacts and close-up splashes

Start with selectable small, medium, and large animal proxies. Estimate transferred momentum from effective mass, velocity change, and entry direction. For sustained motion, calibrate a ram-pressure source using relative velocity, projected contact area, and body orientation. Use the damped local height field from Milestone 1 as the primary interaction solver. A wave-particle patch initialized from the background JONSWAP parameters is an alternative if matching the local and offshore wave spectra becomes a priority.

For strong impacts, allocate a bounded local smoothed particle hydrodynamics (SPH) region. Size its initial radius, particle budget, and lifetime from the event. Partition the initial impulse between the grid and particles. Compute particle neighborhoods, density, pressure, viscosity, and integration on the GPU. Track the active extent, reclaim particle slots once, and return remaining vertical momentum on re-entry to generate secondary rings.

| Reconstruction step | Implementation decision |
|---|---|
| Establish a screen-space baseline | Render nearest particle depth, apply horizontal and vertical bilateral depth filters, and reconstruct view-space normals by finite differences. Reject invalid samples and preserve depth discontinuities. Blend attached surfaces using depth and coverage while retaining detached droplet silhouettes. |
| Diagnose a gelatinous appearance | Freeze a particle snapshot and compare spherical and anisotropic kernels under identical lighting. Inspect the moving particles separately for excessive numerical damping or absent spray. This distinguishes a reconstruction artifact from missing simulated motion. |
| Recover sheets and filaments | Apply PCA to weighted neighboring particle positions. Align ellipsoidal kernels with the resulting axes, bound axis ratios and minimum thickness, and use spherical kernels for isolated droplets. |
| Refine close-ups | Accumulate ellipsoidal density in a narrow-band grid and extract the surface with Marching Cubes. Refine locally where a sheet is undersampled. If the particle motion itself lacks detail, increase local particle density and retune mass, neighbor radius, and time step together. Uniform 3D refinement grows cubically. |
| Finish the surface | If residual bumps persist, test gentle neighbor-guided mesh smoothing in dense regions. Preserve sparse spray. Composite each region once and inspect highlights across the join with the ocean. |

**Acceptance.** Replay the three proxy sizes under a fixed camera. Compare splash silhouette, sheet thickness, detached droplets, and secondary rings. Stress simultaneous impacts until the particle pool reaches capacity and check for duplicate indices, lost slots, and double-counted momentum.

## Milestone 5 — Fishing, wakes, and underwater views

Implement bait detection, approach, bite, float response, reeling, and catch resolution. Sample the combined wave height and velocity on the GPU at multiple points beneath and beside the float. Compute buoyant force and torque from immersion. Feed contact forces back through the same event interface.

Distribute a moving pressure source along fish and hull trajectories. Use the damped solver for local ripples and foam transport. For a Kelvin wake, implement an iWave-style dispersive solver and test the trailing wave pattern over a range of steady speeds. The constant-speed wave equation in Milestone 1 alone cannot reproduce the wavelength-dependent propagation of deep-water wakes.

Blend above-water and underwater rendering as the camera crosses the displaced surface. Add Snell’s window, total internal reflection, and per-channel underwater fog. Use surface transmission, occlusion, and bottom depth to drive light shafts and caustics.

**Acceptance.** Record a complete bite-to-catch sequence above and below the surface. Inspect float stability, wake direction during turns, waterline continuity, and the change in underwater visibility with depth.

## Vulkan integration and final verification

- Compile and validate compute shaders with the Vulkan SDK. Begin with one graphics-and-compute queue, 16 × 16 grid workgroups with bounds checks, and double-buffered R32F height images. Use aligned storage-buffer records of 32 bytes per event and 64 bytes per particle. Verify host and shader offsets.
- Make upload writes visible to compute, order dependent compute dispatches, and make simulation outputs visible to vertex and fragment reads. Transition particle depth from attachment writes to filter reads, then expose filtered depth to composition. Protect staging and simulation resources across frames. If work moves to separate queues, add semaphore ordering and transfer queue-family ownership where required.
- Preallocate particle storage and separate allocation and recycling dispatches. Check support for the required atomic operations. For scaled signed-integer impulse accumulation, bound the scale using the worst-case per-cell impulse sum per step.
- Run synchronization validation during rapid impacts, multiple simulation steps per frame, resize, and quality changes. Exercise long sessions to verify damping, resource reuse, and stable particle counts.
- Capture GPU timestamps for FFT, local waves, SPH, particle depth, tile culling, both bilateral passes, normal reconstruction, and composition. Report median and 95th-percentile timings with the GPU, resolution, and quality preset. Keep close-up splashes at full resolution for the reference captures. Evaluate half-resolution filtering for distant spray against the same silhouettes and highlights.

The final demo should include a quiet-water impact, a moving wake, a close-up splash with re-entry, and a complete fishing interaction. Save fixed-camera captures and per-pass timings alongside the settings needed to reproduce each scene.
