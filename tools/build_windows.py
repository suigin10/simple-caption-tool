"""Build a portable onedir Windows package; no models or user cache are bundled."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Reuse an installed host PyInstaller when building from a venv without one.
    try:
        import PyInstaller.__main__
    except ImportError:
        host_site = Path(sys.base_prefix) / "Lib" / "site-packages"
        if not (host_site / "PyInstaller").exists():
            raise SystemExit("Install PyInstaller in the build environment first")
        sys.path.append(str(host_site))
        import PyInstaller.__main__
    dist, work = args.dist.resolve(), args.work.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    flags = [str(root / "tools" / "frozen_entry.py"), "--name", "simple-caption-tool", "--onedir", "--windowed",
             "--noupx", "--distpath", str(dist), "--workpath", str(work / "pyinstaller"),
             "--specpath", str(work), "--paths", str(root),
             "--add-data", str(root / "captioner" / "catalog.json") + ":captioner",
             "--add-data", str(root / "captioner" / "icons") + ":captioner/icons",
             "--hidden-import", "PySide6.QtSvg"]
    for name in ("PyQt5", "PyQt6", "PySide2", "tkinter", "matplotlib", "numpy", "scipy", "pandas", "torch", "IPython", "pytest"):
        flags += ["--exclude-module", name]
    # Limit native dependency discovery to this build and Windows system libraries.
    # Other applications can place incompatible ICU/Qt DLLs on PATH.
    site = Path(sys.prefix) / "Lib" / "site-packages"
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    os.environ["PATH"] = os.pathsep.join(str(p) for p in (
        site / "PySide6", site / "shiboken6", windows / "System32", windows,
        Path(sys.base_prefix), Path(sys.base_prefix) / "Scripts"))
    PyInstaller.__main__.run(flags)
    bundle = dist / "simple-caption-tool"
    internal = bundle / "_internal"
    # Windows provides ICU. Do not shadow it with DLLs from Conda/Poppler/etc.
    (internal / "icuuc.dll").unlink(missing_ok=True)
    for name in ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll", "MSVCP140_1.dll", "MSVCP140_2.dll"):
        source_dll = site / "PySide6" / name
        if source_dll.exists():
            shutil.copy2(source_dll, internal / name)
    # This QWidget application does not use Qt Quick, PDF or virtual keyboards.
    # Avoid shipping their optional plugins and transitive native libraries.
    qt = internal / "PySide6"
    unused = [qt / "plugins" / "platforminputcontexts" / "qtvirtualkeyboardplugin.dll",
              qt / "plugins" / "imageformats" / "qpdf.dll"]
    for pattern in ("Qt6VirtualKeyboard.dll", "Qt6Qml*.dll", "Qt6Quick*.dll", "Qt6Pdf*.dll"):
        unused.extend(qt.glob(pattern))
    for path in unused:
        path.unlink(missing_ok=True)
    for name in ("README.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.txt"):
        shutil.copy2(root / name, bundle / name)
    shutil.copytree(root / "licenses", bundle / "licenses", dirs_exist_ok=True)
    # Keep a rebuildable application source copy with dynamically replaceable Qt DLLs.
    source = bundle / "source"
    source.mkdir(exist_ok=True)
    for directory in ("captioner", "tools", "tests", "licenses"):
        shutil.copytree(root / directory, source / directory,
                        ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    for name in ("pyproject.toml", "requirements-tested.txt", "README.md", "simple-caption-tool.cmd", "THIRD_PARTY_NOTICES.txt"):
        shutil.copy2(root / name, source / name)
    print("Portable Windows build:", bundle)


if __name__ == "__main__":
    main()
