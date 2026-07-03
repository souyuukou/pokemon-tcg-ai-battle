"""Create a competition submission zip from sample_submission/."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sample_submission"
OUT = ROOT / "submission.zip"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    rel = path.relative_to(SRC)
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return path.is_file()


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    if not SRC.is_dir():
        raise SystemExit(f"missing directory: {SRC}")

    required = [
        SRC / "main.py",
        SRC / "deck.csv",
        SRC / "model.nnue",
        SRC / "deck_catalog.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing required files: {', '.join(missing)}")

    native = [
        SRC / "pokemon_pvs.dll",
        SRC / "libpokemon_pvs.so",
        SRC / "libpokemon_pvs.dylib",
    ]
    present = [path.name for path in native if path.exists()]
    print(f"native libraries bundled: {', '.join(present) or 'none'}")
    if not any(path.exists() for path in native):
        print("warning: no native PVS library; fallback.py will be used at runtime")
    elif not (SRC / "libpokemon_pvs.so").exists():
        print("warning: libpokemon_pvs.so missing; Linux submissions will use fallback")
    else:
        linux_native = SRC / "libpokemon_pvs.so"
        build_inputs = [
            ROOT / "CMakeLists.txt",
            ROOT / "cpp" / "src" / "engine.cpp",
            *sorted((ROOT / "cpp" / "include").glob("*.hpp")),
            *sorted((ROOT / "cpp" / "include").glob("*.h")),
        ]
        newest_input = max(path.stat().st_mtime for path in build_inputs)
        if linux_native.stat().st_mtime < newest_input:
            raise SystemExit(
                "libpokemon_pvs.so is older than its C++ build inputs; "
                "rebuild the Linux library before packaging"
            )

    cg_libs = list((SRC / "cg").glob("libcg*.so")) + list((SRC / "cg").glob("cg.dll"))
    if not cg_libs:
        print("warning: no cg native library under sample_submission/cg/")

    files = sorted(path for path in SRC.rglob("*") if should_include(path))
    if out_path.exists():
        out_path.unlink()

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(SRC).as_posix())

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"created {out_path} ({len(files)} files, {size_mb:.2f} MiB)")


if __name__ == "__main__":
    main()
