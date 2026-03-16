# RA Project Packaging Guide (Windows + macOS)

This setup creates a one-click local app for non-technical users.

## Fastest build path (recommended)

Use the single cross-platform build entrypoint:

- Windows: `build_release.bat`
- macOS: `python3 build_release.py` (or `build_release.command`)

It auto-detects OS and builds the correct native package.

## What users do

1. Download the packaged folder (or zip) you provide.
2. Open the `RA-Launcher` folder.
3. Double-click `RA Launcher.exe`.
4. Their browser opens automatically to the local app.
5. Keep the launcher window open while using the app.

No IDE and no terminal commands are needed for end users.

## Build a release (for you)

From the project root (`RA-Prototype`), run:

- `build_windows_package.bat` (double-click), or
- `powershell -ExecutionPolicy Bypass -File .\build_windows_package.ps1`

After it finishes, share `release\RA-Launcher-windows.zip`.

## Build a macOS zip package

Important: You must run this on a Mac (you cannot build a Mac app bundle from Windows).

From project root (`RA-Prototype`) on macOS:

- `chmod +x ./build_macos_package.sh ./build_macos_package.command`
- `./build_macos_package.sh`

Output:

- `release-macos/RA-Launcher-macOS.zip`

Share `RA-Launcher-macOS.zip` with Mac users.

## Build a single installer EXE (recommended for non-technical users)

1. Install Inno Setup 6 from:
   - https://jrsoftware.org/isinfo.php
2. From project root, run:
   - `build_windows_installer.bat` (double-click), or
   - `powershell -ExecutionPolicy Bypass -File .\build_windows_installer.ps1`
3. Share this file:
   - `release\installer\RA-Launcher-Setup.exe`

## Notes

- The app runs only on the local machine (`127.0.0.1`).
- The user must keep all files inside `RA-Launcher` together.
- To stop the app, close the `RA Launcher.exe` window.
- If Windows SmartScreen appears, click **More info** then **Run anyway** (common for unsigned apps).
- Users still need a valid OpenAI API key in the app flow where analysis is run.
- `.exe` files are Windows-only. Mac users need the macOS package (`RA Launcher.app` inside `RA-Launcher-macOS.zip`).
- On macOS, first launch may be blocked by Gatekeeper. Right-click the app, choose **Open**, then confirm.
