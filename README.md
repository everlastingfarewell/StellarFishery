# StellarFishery

A fixed-step Vulkan water simulation for Python: a 128 x 128 damped wave field
that reacts to impacts, spectral ocean cascades on a stitched clipmap, water
optics (reflection, refraction, crest lighting) and persistent foam.

| Document | Contents |
| --- | --- |
| [docs/plan.en.md](docs/plan.en.md) | Full milestone plan, acceptance criteria and Vulkan integration notes |
| [docs/milestone1.md](docs/milestone1.md) | Calm-water impact simulator and its replay measurements |
| [docs/ocean.md](docs/ocean.md) | Spectral cascades, optics and foam |
| [docs/brick.md](docs/brick.md) | TrimUI Brick Pro framebuffer demo, installation and hardware results |

## Repository layout

```
stellar/            the package
  config.py         paths and grid constants (metres, seconds, newtons)
  platform.py       device selection, shader modules, platform capabilities
  simulation.py     fixed-step height field (compute) and contact bookkeeping
  spectrum.py       JONSWAP seeding and the separable inverse FFT
  renderer.py       opaque pass, water surface, foam advection, picking
  mesh.py           stitched clipmap vertex and index buffers
  brick.py          capability detection for the TRIMUI Brick
shaders/            WGSL modules, joined in the order renderer.py lists them
spv/                prebuilt SPIR-V per module (tools/build-spv.py)
data/               bytecode and capability files shipped with the platform
examples/demo.py    interactive window
tests/              acceptance replays (write captures/)
tools/              environment, Vulkan driver, SPIR-V and Brick deployment scripts
captures/           recorded replays and measurements referenced by the docs
```

`stellar.renderer` joins `camera.wgsl` + `bathymetry.wgsl` + `ocean.wgsl` +
`surface.wgsl` into one module, so the shader files are grouped by module, not by
file: `bathymetry.wgsl` defines the sand bank used by both the opaque pass and
the water. Entry points per module:

| Module | Files | Entry points |
| --- | --- | --- |
| `screen` | camera, bathymetry, opaque | `fullscreen` (vertex), `opaque` (fragment) |
| `sea` | camera, bathymetry, ocean, surface | `vertex`, `fragment`, `probe` (compute) |
| `foam` | bathymetry, ocean, foam | `foam` (compute) |
| `spectrum` | fft | `rows`, `columns` (compute) |
| height field | `shaders/wave.comp` (GLSL) | `main` (compute) |

Shader modules are WGSL, which wgpu compiles with naga at runtime. On a platform
without that compiler (the Brick), the renderer loads `spv/<module>.spv`
instead; `data/platform.npy` records which capabilities the machine has.

## Requirements

- Python >= 3.13 (tested on 3.13 and 3.14)
- A Vulkan 1.1+ driver. On Arch Linux: `sudo pacman -S vulkan-intel` (or
  `vulkan-radeon`). The LunarG SDK is not required; `glslc` from `shaderc`
  only has to be on `PATH` to rebuild the height-field shader.
- `glfw` for the interactive window (`requirements-gui.txt`). The acceptance
  tests render offscreen and do not need it.

Without a system driver, `tools/setup-vulkan-icd.sh` installs `vulkan-intel`
into `~/.local/vulkan-intel` for the current user and `tools/env.sh` exports
`VK_DRIVER_FILES` for it.

## Install

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-gui.txt
```

or equivalently `uv pip install --python .venv/bin/python -e '.[gui]'`.
The `wgpu` wheel bundles wgpu-native, so no Rust toolchain is needed.

## Run

```
./run.sh
```

runs `python -m examples.demo` with the project virtualenv and the driver
environment. Manually:

```
. tools/env.sh
.venv/bin/python -m examples.demo      # or without .: PYTHONPATH=. .venv/bin/python -m examples.demo
```

| Input | Action |
| --- | --- |
| left press + release | aim at the surface and strike it (hold up to 1 s for the 24 N·s maximum impulse) |
| right drag | orbit |
| middle drag | zoom |
| W / A / S / D | move the camera over the sea |
| Q / E | rotate the sun |
| 1 / 2 | zero background energy / low wind |
| G | toggle the 320 m analytical swell |

Close the window to exit.

## Verify

```
. tools/env.sh
.venv/bin/python -c "from tests.test_acceptance import verify_contacts; print(verify_contacts())"
.venv/bin/python -m tests.test_acceptance        # rewrites captures/ and measurements.csv
.venv/bin/python -m tests.test_ocean_acceptance  # rewrites captures/ocean/
```

The first command checks the impulse, momentum and scroll bookkeeping of the
height field and prints the first-step central depression (about -0.023575 m).
The two suites render several minutes of replays.

## Rebuilding shader bytecode

```
python tools/build-spv.py                     # WGSL -> spv/<module>.spv (needs naga)
glslangValidator -V -S comp shaders/wave.comp -o data/water.spv
```

## Troubleshooting

- `Request adapter failed ... vulkan drivers/libraries could not be loaded` -
  no ICD is visible. Install `vulkan-intel` (or `vulkan-radeon`) and, for the
  user-local install, export `VK_DRIVER_FILES=~/.local/vulkan-intel/intel_icd.json`.
- `Install the Vulkan SDK to provide glslc` - neither `glslc` nor
  `data/water.spv` is available; install `shaderc` (and `spirv-tools`) or ship
  the prebuilt bytecode.
- `MESA-*: failed to open ...` after a Mesa upgrade - the user-local driver is
  pinned to the Mesa version it was built for; rerun
  `tools/setup-vulkan-icd.sh`.
- `Project must be installed` / `No module named stellar` - run from the
  repository root with `PYTHONPATH=.` or use `./run.sh`.
