# -*- mode: python ; coding: utf-8 -*-
"""Windows build, in one-file or one-folder form.

Set MCBUILDER_ONEFILE=0 for the folder build. Both are shipped because a
one-file executable unpacks itself into %TEMP% on every launch and runs from
there, which antivirus software blocks often enough to matter -- and when it
does, the program dies before it can print anything. The folder build has no
extraction step, so it is the fallback when the single file will not start.

Console mode is mandatory either way: the tool prompts with input() during
setup and prints progress while building, none of which exists in a windowed
build.
"""

import os

ONEFILE = os.environ.get("MCBUILDER_ONEFILE", "1") != "0"

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

common = dict(
    name="mcbuilder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
else:
    # The folder build keeps binaries and data beside the launcher instead of
    # bundling them inside it, so nothing is written to %TEMP% at startup.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="mcbuilder",
    )
