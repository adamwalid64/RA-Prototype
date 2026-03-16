# Start Here (Cross-Platform)

You now have a single build entrypoint that creates the correct package for the OS you run it on.

## Build (for you)

- On **Windows**: double-click `build_release.bat`
- On **macOS**: run `build_release.command` (or `python3 build_release.py`)

This automatically builds:

- Windows -> `release/RA-Launcher-windows.zip`
- macOS -> `release-macos/RA-Launcher-macOS.zip`

## Share with end users

- Send Windows users: `RA-Launcher-windows.zip`
- Send macOS users: `RA-Launcher-macOS.zip`

## End-user install

1. Download zip
2. Extract zip
3. Run app:
   - Windows: `RA Launcher.exe`
   - macOS: `RA Launcher.app` (right-click -> Open first time if needed)

Each OS needs its own native package. A Windows `.exe` cannot run on macOS, and a macOS `.app` cannot run on Windows.
