"""Compile the WGSL shader modules to SPIR-V, one file per module.

Each module (its WGSL files joined in runtime order) is compiled into
`spv/<module>.spv`, which is what `stellar.renderer` loads on platforms without
a WGSL compiler, such as the TRIMUI Brick.

Requires `naga` (cargo install naga-cli), the WGSL frontend wgpu itself uses;
glslc's GLSL frontend cannot read WGSL.

    python tools/build-spv.py              # host build
    python tools/build-spv.py --naga PATH  # explicit naga binary
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Kept in step with stellar/renderer.MODULES and stellar/spectrum.py.
MODULES = {
    "screen": ["camera.wgsl", "bathymetry.wgsl", "opaque.wgsl"],
    "sea": ["camera.wgsl", "bathymetry.wgsl", "ocean.wgsl", "surface.wgsl"],
    "foam": ["bathymetry.wgsl", "ocean.wgsl", "foam.wgsl"],
    "spectrum": ["fft.wgsl"],
}
ENTRY_POINTS = {
    "screen": ["fullscreen", "opaque"],
    "sea": ["vertex", "fragment", "probe"],
    "foam": ["foam"],
    "spectrum": ["rows", "columns"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "spv"))
    parser.add_argument("--naga", default="naga")
    args = parser.parse_args()
    naga = shutil.which(args.naga) or args.naga
    if not Path(naga).exists() and not shutil.which(naga):
        raise SystemExit("naga not found: cargo install naga-cli, or pass --naga PATH")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # naga compiles every entry point of a module into one SPIR-V file, and
    # wgpu picks the entry point by name, so one file per module is enough.
    for module, files in MODULES.items():
        code = "\n".join((ROOT / "shaders" / f).read_text() for f in files)
        tmp = out / f"{module}.wgsl"
        tmp.write_text(code)
        subprocess.run([naga, str(tmp), str(out / f"{module}.spv")], check=True)
        tmp.unlink()
        print((out / f"{module}.spv").relative_to(ROOT),
              "entries:", ", ".join(ENTRY_POINTS[module]))


if __name__ == "__main__":
    sys.exit(main())
