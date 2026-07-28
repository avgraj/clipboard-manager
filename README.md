# Clipboard Manager

A background clipboard history app for **Windows**.

Press a hotkey from any app to search, pin, organize, and reuse anything you have copied. History is stored locally in SQLite, so it survives restarts (not only pinned items).

## Features

- Global hotkey (default: `Ctrl+B`) opens the popup from anywhere
- Full clipboard history with timestamps, saved on disk
- Live search
- Pin items to keep them at the top
- Folders (Work, Code, Links, or your own)
- Image clipboard support with thumbnails
- System tray icon (Show / Quit)
- Title-bar **?** help tip (shows how to use the terminal helper)
- Terminal helper: `clipboard.cmd` (`start`, `stop`, `open`, `close`, …)
- Keyboard-first: arrows, Enter to copy, `Ctrl+P` pin, Delete, Esc, Tab for sidebar

## Requirements

- Windows 10 or 11
- Python 3.10+
- Packages in `requirements.txt`

## Project files

```
clipboard_manager.py   # main app
clipboard.cmd          # start / stop / open / close / …
requirements.txt       # Python dependencies
README.md
.gitignore
```

## Install (step by step)

### 1. Install Python

1. Download Python from https://www.python.org/downloads/
2. Run the installer
3. Enable **Add python.exe to PATH**
4. Finish the install

Check in a **new** terminal:

```bat
python --version
```

### 2. Get the project

Clone:

```bat
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

Or download the ZIP from GitHub, extract it, and open that folder in a terminal.

### 3. Install dependencies

```bat
pip install -r requirements.txt
```

### 4. Run the app

From the project folder:

```bat
clipboard.cmd start
```

Or:

```bat
pythonw clipboard_manager.py
```

If something fails, use a console so you can see errors:

```bat
python clipboard_manager.py
```

You should see a tray icon. Press `Ctrl+B` to open the window.

## Daily use

| Action | How |
|--------|-----|
| Open popup | `Ctrl+B` or `clipboard.cmd open` |
| Search | Type in the search box |
| Copy an item | Select it + Enter, or click the copy button |
| Pin / unpin | `Ctrl+P` or the pin control on the row |
| Delete item | `Delete` |
| Close popup | `Esc`, ✕, or `clipboard.cmd close` |
| Quit app | Tray → **Quit**, or `clipboard.cmd stop` |
| Help tip | Click **?** in the title bar |

### Terminal commands

Run from the project folder:

```bat
clipboard.cmd start
clipboard.cmd stop
clipboard.cmd open
clipboard.cmd close
clipboard.cmd toggle
clipboard.cmd restart
clipboard.cmd status
clipboard.cmd help
```

| Command | What it does |
|---------|----------------|
| `start` | Start in the background (tray) |
| `stop` | Quit completely |
| `open` | Show the popup (starts app if needed) |
| `close` | Hide the popup (app stays in tray) |
| `toggle` | Show or hide the popup |
| `restart` | Stop, then start |
| `status` | Running or not |
| `help` | List commands |

Aliases: `on`/`run` → start · `off`/`quit`/`exit` → stop · `show` → open · `hide` → close

#### Optional: run from any terminal

Create `%USERPROFILE%\bin\clipboard.cmd` with:

```bat
@echo off
"C:\full\path\to\this\project\clipboard.cmd" %*
```

Add `%USERPROFILE%\bin` to your user PATH, open a new terminal, then:

```bat
clipboard start
clipboard open
```

### In-app help (?)

1. Open the popup (`Ctrl+B`)
2. Click **?** in the title bar
3. The search bar shows: `type clipboard in terminal`

Use the terminal helper (`clipboard.cmd`) for start / stop / open / close and the other commands listed above.

## Run on Windows startup

1. Press `Win+R`
2. Type `shell:startup` and press Enter
3. Add a shortcut or a `.vbs` file:

**Shortcut**

- **Target:**  
  `"C:\path\to\pythonw.exe" "C:\path\to\this\project\clipboard_manager.py"`
- **Start in:**  
  `C:\path\to\this\project`

**Or `.vbs` (no console flash)**

```vbs
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\path\to\this\project"
sh.Run """C:\path\to\pythonw.exe"" ""C:\path\to\this\project\clipboard_manager.py""", 0, False
```

Replace paths with your real ones.

## Change the hotkey

In `clipboard_manager.py` near the top:

```python
HOTKEY = "ctrl+b"
```

Examples: `"ctrl+shift+v"`, `"alt+c"`, `"ctrl+alt+v"`.

Save, then:

```bat
clipboard.cmd restart
```

## Data location

```
%USERPROFILE%\.clipboard_manager\
  history.db
  images\
  command.txt    (used by clipboard.cmd open/close/stop)
  app.pid
```

All data stays on your PC. Nothing is uploaded.

## Notes

- Windows only
- Hotkey may not work while an elevated (Admin) window is focused
- Clipboard is checked about every 0.4s in the background

## License

Use and modify freely for personal or project use.
