Two downloads, same program. Try **mcbuilder.exe** first.

- **mcbuilder.exe** — one file, nothing to install.
- **mcbuilder-folder.zip** — use this if the single file does nothing when you double-click it. Unzip anywhere and run `mcbuilder.exe` from inside the folder. The one-file build unpacks itself into `%TEMP%` on every launch, which some antivirus software blocks silently; this one has no extraction step.

Windows SmartScreen will warn about an unsigned download: choose **More info**, then **Run anyway**. If a download does nothing at all, run it from PowerShell (`.\mcbuilder.exe blocks`) so the error stays on screen, and check `Get-MpThreatDetection` — antivirus false positives on packaged Python programs are common.

Double-click for a guided menu, or run it from a terminal for the full command line (`mcbuilder.exe --help`).

Minecraft Java Edition on Windows. The README covers the one-time setup — learn the F3 font, then calibrate the mouse — and the two preconditions that catch people out: flat ground under the mural, and Windows "Enhance pointer precision" turned off.
