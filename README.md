



<div align="center">

# Clipboard Manager

**A fast, keyboard-driven clipboard history app for Windows.**

Press a hotkey from anywhere to search, pin, and reuse anything you've copied — text or images — with history saved locally in SQLite.

[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows)](https://github.com/avgraj/clipboard-manager)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-free%20to%20use-green)](#license)










<p align="center">
  <table>
    <tr>
      <td align="center">
        <img src="https://github.com/user-attachments/assets/1aa9f5d8-9dc9-4e7c-96f2-5a504fc9687d" width="320" alt="Clipboard Manager popup - view 1">
      </td>
      <td align="center">
        <img src="https://github.com/user-attachments/assets/0e36afbd-707c-4a15-950c-7ec0fd743db8" width="320" alt="Clipboard Manager popup - view 2">
      </td>
    </tr>
  </table>
</p>

</div>

---

## Features

- **Global hotkey** (`Ctrl+B` by default) — open the popup from any app
- **Full clipboard history** with timestamps, persisted to disk (survives restarts)
- **Live search** across your history
- **Pin** important items to keep them at the top
- **Folders** — Work, Code, Links, or your own custom categories
- **Image clipboard support** with thumbnails
- **System tray icon** — quick Show / Quit
- **Keyboard-first UX** — arrows, Enter to copy, `Ctrl+P` to pin, Delete, Esc, Tab for sidebar
- **Terminal helper** (`clipboard.cmd`) — `start`, `stop`, `open`, `close`, and more
- **In-app help** — click the `?` in the title bar anytime

---

## Requirements

- Windows 10 or 11
- Python 3.10+
- Dependencies listed in `requirements.txt`

---

## Installation

### 1. Install Python

1. Download Python from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer
3. Enable **Add python.exe to PATH**
4. Finish the install

Verify in a **new** terminal:
```bash
python --version
```

### 2. Get the project

**Clone:**
```bash
git clone https://github.com/avgraj/clipboard-manager.git
cd clipboard-manager
```

**Or** download the [ZIP](https://github.com/avgraj/clipboard-manager/archive/refs/heads/main.zip), extract it, and open that folder in a terminal.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
clipboard.cmd start
```

Or directly:
```bash
pythonw clipboard_manager.py
```

> **Troubleshooting:** if something fails silently, run it in a console window so you can see errors:
> ```bash
> python clipboard_manager.py
> ```

You should see a tray icon appear. Press `Ctrl+B` to open the popup.

---

## Project structure

```
clipboard-manager/
├── clipboard_manager.py   # Main application
├── clipboard.cmd          # start / stop / open / close / ...
├── requirements.txt       # Python dependencies
├── README.md
└── .gitignore
```

---

## Daily use

| Action | How |
|---|---|
| Open popup | `Ctrl+B` or `clipboard.cmd open` |
| Search | Type in the search box |
| Copy an item | Select it + `Enter`, or click the copy button |
| Pin / unpin | `Ctrl+P` or the pin control on the row |
| Delete item | `Delete` |
| Close popup | `Esc`, the close button, or `clipboard.cmd close` |
| Quit app | Tray → **Quit**, or `clipboard.cmd stop` |
| Help tip | Click **?** in the title bar |

### Terminal commands

Run from the project folder:

```bash
clipboard.cmd start     # start in the background (tray)
clipboard.cmd stop      # quit completely
clipboard.cmd open      # show the popup (starts app if needed)
clipboard.cmd close     # hide the popup (app stays in tray)
clipboard.cmd toggle    # show or hide the popup
clipboard.cmd restart   # stop, then start
clipboard.cmd status    # check if running
clipboard.cmd help      # list commands
```

**Aliases:** `on` / `run` → `start`  ·  `off` / `quit` / `exit` → `stop`  ·  `show` → `open`  ·  `hide` → `close`

<details>
<summary><b>Optional: run <code>clipboard</code> from any terminal, not just the project folder</b></summary>

<br>

Create `%USERPROFILE%\bin\clipboard.cmd` with:

```bat
@echo off
"C:\full\path\to\this\project\clipboard.cmd" %*
```

Add `%USERPROFILE%\bin` to your user PATH, open a new terminal, then run `clipboard start` / `clipboard open` from anywhere.

</details>

---

## Configuration

### Change the hotkey

Edit the top of `clipboard_manager.py`:

```python
HOTKEY = "ctrl+b"
```

Other examples: `"ctrl+shift+v"`, `"alt+c"`, `"ctrl+alt+v"`.

Then apply the change:
```bash
clipboard.cmd restart
```

### Run on Windows startup

1. Press `Win+R`, type `shell:startup`, press Enter
2. Add a shortcut or a `.vbs` file to that folder:

**Shortcut**
- **Target:** `"C:\path\to\pythonw.exe" "C:\path\to\this\project\clipboard_manager.py"`
- **Start in:** `C:\path\to\this\project`

**Or a `.vbs` file (no console flash):**
```vbs
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\path\to\this\project"
sh.Run """C:\path\to\pythonw.exe"" ""C:\path\to\this\project\clipboard_manager.py""", 0, False
```

Replace all paths with your actual project location.

---

## Data location

```
%USERPROFILE%\.clipboard_manager\
├── history.db     # clipboard history (SQLite)
├── images\        # saved image thumbnails
├── command.txt    # used by clipboard.cmd open/close/stop
└── app.pid
```

**Everything stays local.** Nothing is uploaded anywhere.

---

## Notes

- Windows only (no macOS/Linux support planned)
- The hotkey may not register while an elevated (Admin) window is focused
- Clipboard is checked about every 0.4s in the background

---

## License

Use and modify freely for personal or project use.

---

<div align="center">

Made with a lot of `Ctrl+V`

</div>



