# -*- mode: python ; coding: utf-8 -*-
"""One-file Windows build.

Console mode is mandatory: the tool prompts with input() during setup and
prints progress while building, none of which exists in a windowed build.
"""

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    # mss picks its backend at runtime, so PyInstaller's static analysis does
    # not see the Windows one.
    hiddenimports=["mss.windows"],
    hookspath=[],
    runtime_hooks=[],
    # Nothing here draws a GUI or runs tests; excluding them keeps the
    # download from doubling in size.
    excludes=[
        "tkinter",
        "matplotlib",
        "pytest",
        "IPython",
        "numpy.distutils",
        "PIL.ImageQt",
        "PIL.ImageTk",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mcbuilder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
