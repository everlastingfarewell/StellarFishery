# Milestone 1 · Calm-water impact

Use Python 3.13 and a Vulkan driver with support for read/write R32F and RG32F storage images. `glslc` and `spirv-val` (Arch: `shaderc`, `spirv-tools`) are compiled against at start-up; the LunarG SDK only has to provide them if they are not packaged, and `data/water.spv` covers platforms without them. From the repository root, install and run:

    uv pip install --python .venv/bin/python -r requirements-gui.txt
    .venv/bin/python -m examples.demo       # or ./run.sh

Right-drag to orbit, middle-drag vertically to zoom, and use WASD to move across the sea. Press the left button to aim and release to strike the surface along the captured ray. Holding for one second gives the maximum impulse of 24 N·s.

The 128 × 128 patch uses 0.125 m cells, 3 m/s propagation and a 1/60 s integration step. Its 14-cell damping border moves with the interaction region. With an effective contact thickness of 0.08 m and a 0.45 m footprint radius, the reference 24 N·s downward impulse produces a 23.58 mm first-step central depression. Picking and buoyancy probes intersect the same triangles drawn for the latest completed tick.

## Fixed-camera replay

Run `python -m tests.test_acceptance` to regenerate the captures and measurements in `captures/`. The replay advances at controlled 30 and 60 render frames per simulated second. The lossless WebP recordings sample every 0.1 s. The four-impact burst starts at 0, 0.012, 0.17 and 0.32 s, including two impacts in the first integration step. The suite also checks stepwise sustained force, vertical and horizontal impulse totals, patch-edge normalization, and preservation of overlapping cells after scrolling.

On AMD Radeon 780M Graphics (Vulkan), every cell matched exactly across frame rates at all 60 shared samples in each replay. For the single impact, the strongest disturbance on the positive x axis moved from 1.25 m at 0.5 s to 2.75 m at 1 s and 5.75 m at 2 s. Peak amplitudes at those times were 20.90, 12.75 and 6.56 mm. At 2.5 s the outgoing disturbance peaked at 4.99 mm beyond 7 m. A smaller return was visible inside the central 2 m, measuring 1.35 mm at 5 s. The burst measured 5.16 mm there at the same time. These inner-region measurements include the residual disturbance as well as the returning wave.
