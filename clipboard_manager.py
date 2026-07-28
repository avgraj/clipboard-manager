"""
Clipboard Manager
Keyboard-first clipboard history with folders, images, pin, modern dark UI.
"""

import hashlib
import os
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime
from io import BytesIO

import keyboard
import pyperclip
from PIL import ImageGrab

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QTimer,
    QSize,
    QRect,
    QRectF,
    QThread,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QBrush,
    QPen,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSplitter,
    QStyledItemDelegate,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
    QStyle,
)

# ---------- config ----------
HOTKEY = "ctrl+b"
MAX_ITEMS = 500
POLL_INTERVAL = 0.4
DB_DIR = os.path.join(os.path.expanduser("~"), ".clipboard_manager")
DB_PATH = os.path.join(DB_DIR, "history.db")
IMAGES_DIR = os.path.join(DB_DIR, "images")
CMD_PATH = os.path.join(DB_DIR, "command.txt")
PID_PATH = os.path.join(DB_DIR, "app.pid")

BG = "#14141f"
BG_ALT = "#1c1c2e"
BG_HOVER = "#252540"
BG_SELECTED = "#2a3a5c"
FG = "#e8e8ef"
FG_DIM = "#8888a0"
ACCENT = "#5b9fd4"
PIN_COLOR = "#e8b84a"
BORDER = "#2e2e45"
SURFACE = "#181825"
COPY_BTN = "#3d7ec9"
PIN_BTN = "#3a3a28"
SIDEBAR_BG = "#12121c"

WINDOW_W = 620
WINDOW_H = 480
SIDEBAR_W = 148
ROW_H = 48
BTN_SIZE = 28


# ---------- database ----------
class ClipboardDB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT,
                    created_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    item_type TEXT NOT NULL DEFAULT 'text',
                    folder_id INTEGER,
                    image_path TEXT,
                    image_hash TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0
                )
            """)
            cols = {c[1] for c in cur.execute("PRAGMA table_info(history)").fetchall()}
            for col, sql in (
                ("item_type", "ALTER TABLE history ADD COLUMN item_type TEXT NOT NULL DEFAULT 'text'"),
                ("folder_id", "ALTER TABLE history ADD COLUMN folder_id INTEGER"),
                ("image_path", "ALTER TABLE history ADD COLUMN image_path TEXT"),
                ("image_hash", "ALTER TABLE history ADD COLUMN image_hash TEXT"),
            ):
                if col not in cols:
                    cur.execute(sql)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_history_text ON history(text)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_history_pinned ON history(pinned)")
            self.conn.commit()

    def get_folders(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id, name FROM folders ORDER BY sort_order, name COLLATE NOCASE")
            return cur.fetchall()

    def add_folder(self, name):
        name = name.strip()
        if not name:
            return None
        with self.lock:
            try:
                cur = self.conn.cursor()
                cur.execute("INSERT INTO folders (name) VALUES (?)", (name,))
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def rename_folder(self, fid, new_name):
        new_name = new_name.strip()
        if not new_name:
            return False
        with self.lock:
            try:
                self.conn.execute("UPDATE folders SET name = ? WHERE id = ?", (new_name, fid))
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_folder(self, fid):
        with self.lock:
            self.conn.execute("UPDATE history SET folder_id = NULL WHERE folder_id = ?", (fid,))
            self.conn.execute("DELETE FROM folders WHERE id = ?", (fid,))
            self.conn.commit()

    def add_text(self, text):
        text = text.strip()
        if not text:
            return
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT id, pinned FROM history WHERE text = ? AND item_type = 'text'",
                (text,),
            )
            row = cur.fetchone()
            if row:
                # bump to top; keep pin state
                cur.execute(
                    "UPDATE history SET created_at = ? WHERE id = ?",
                    (now, row[0]),
                )
            else:
                try:
                    cur.execute(
                        "INSERT INTO history (text, created_at, pinned, item_type) "
                        "VALUES (?, ?, 0, 'text')",
                        (text, now),
                    )
                except sqlite3.IntegrityError:
                    cur.execute(
                        "UPDATE history SET created_at = ? WHERE text = ? AND item_type = 'text'",
                        (now, text),
                    )
            self.conn.commit()
            self._enforce_limit()

    def add_image(self, image_path, image_hash):
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT id FROM history WHERE image_hash = ? AND item_type = 'image'",
                (image_hash,),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE history SET created_at = ? WHERE id = ?",
                    (now, row[0]),
                )
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except OSError:
                        pass
            else:
                cur.execute(
                    "INSERT INTO history (created_at, pinned, item_type, image_path, image_hash) "
                    "VALUES (?, 0, 'image', ?, ?)",
                    (now, image_path, image_hash),
                )
            self.conn.commit()
            self._enforce_limit()

    def _enforce_limit(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM history WHERE pinned = 0")
        count = cur.fetchone()[0]
        if count > MAX_ITEMS:
            excess = count - MAX_ITEMS
            cur.execute(
                """
                SELECT id, image_path, item_type FROM history
                WHERE pinned = 0
                ORDER BY created_at ASC LIMIT ?
                """,
                (excess,),
            )
            for item_id, image_path, item_type in cur.fetchall():
                if item_type == "image" and image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except OSError:
                        pass
                cur.execute("DELETE FROM history WHERE id = ?", (item_id,))
            self.conn.commit()

    def search(self, query="", folder_id=None):
        with self.lock:
            cur = self.conn.cursor()
            params = []
            where = []
            if query:
                where.append(
                    "(text LIKE ? OR (item_type = 'image' AND '[Image]' LIKE ?))"
                )
                params.extend([f"%{query}%", f"%{query}%"])
            if folder_id is not None:
                if folder_id == -1:
                    where.append("folder_id IS NULL")
                else:
                    where.append("folder_id = ?")
                    params.append(folder_id)
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""
            cur.execute(
                f"""
                SELECT id, text, created_at, pinned, item_type, image_path, folder_id
                FROM history {where_sql}
                ORDER BY pinned DESC, created_at DESC
                LIMIT 200
                """,
                params,
            )
            return cur.fetchall()

    def set_folder(self, item_id, folder_id):
        with self.lock:
            if folder_id is None or folder_id == -1:
                self.conn.execute(
                    "UPDATE history SET folder_id = NULL WHERE id = ?", (item_id,)
                )
            else:
                self.conn.execute(
                    "UPDATE history SET folder_id = ? WHERE id = ?", (folder_id, item_id)
                )
            self.conn.commit()

    def toggle_pin(self, item_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT pinned FROM history WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if row is None:
                return
            new_val = 0 if row[0] else 1
            cur.execute(
                "UPDATE history SET pinned = ? WHERE id = ?", (new_val, item_id)
            )
            self.conn.commit()
            return new_val

    def delete(self, item_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT image_path FROM history WHERE id = ? AND item_type = 'image'",
                (item_id,),
            )
            row = cur.fetchone()
            if row and row[0] and os.path.exists(row[0]):
                try:
                    os.remove(row[0])
                except OSError:
                    pass
            self.conn.execute("DELETE FROM history WHERE id = ?", (item_id,))
            self.conn.commit()


# ---------- image helpers ----------
def _hash_image(pil_img):
    buf = BytesIO()
    pil_img.convert("RGB").save(buf, "PNG")
    return hashlib.md5(buf.getvalue()).hexdigest()


def _save_image(pil_img):
    os.makedirs(IMAGES_DIR, exist_ok=True)
    path = os.path.join(IMAGES_DIR, f"{uuid.uuid4().hex}.png")
    pil_img.save(path, "PNG")
    return path


def _load_thumbnail(path, max_size=36):
    if not path or not os.path.exists(path):
        return None
    pix = QPixmap(path)
    if pix.isNull():
        return None
    return pix.scaled(
        max_size,
        max_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _get_clipboard_image():
    try:
        img = ImageGrab.grabclipboard()
        if img is not None and hasattr(img, "save"):
            return img
    except Exception:
        pass
    return None


# ---------- clipboard watcher ----------
class ClipboardWatcher(QThread):
    item_added = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._last_text = None
        self._last_image_hash = None
        self._running = True

    def run(self):
        try:
            self._last_text = pyperclip.paste() or ""
        except Exception:
            self._last_text = ""
        while self._running:
            try:
                current = pyperclip.paste()
                if current and current != self._last_text:
                    self._last_text = current
                    self.db.add_text(current)
                    self.item_added.emit()

                img = _get_clipboard_image()
                if img is not None:
                    h = _hash_image(img)
                    if h != self._last_image_hash:
                        self._last_image_hash = h
                        path = _save_image(img)
                        self.db.add_image(path, h)
                        self.item_added.emit()
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    def stop(self):
        self._running = False


# ---------- row delegate ----------
class ClipDelegate(QStyledItemDelegate):
    """Renders each clip row with pin + copy buttons. Click body only selects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered_row = -1
        self.copy_rects = {}
        self.pin_rects = {}

    def set_hovered(self, row):
        self._hovered_row = row

    def paint(self, painter, option, index):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        data = index.data(Qt.ItemDataRole.UserRole)
        if data is None:
            painter.fillRect(option.rect, QColor(SURFACE))
            painter.setPen(QColor(FG_DIM))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "No items")
            return

        item_id, text, created_at, pinned, item_type, image_path, folder_id = data
        rect = option.rect
        row = index.row()
        hovered = self._hovered_row == row
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if selected:
            bg = QColor(BG_SELECTED)
        elif hovered:
            bg = QColor(BG_HOVER)
        else:
            bg = QColor(SURFACE if row % 2 == 0 else BG_ALT)
        painter.fillRect(rect, bg)

        if pinned:
            painter.fillRect(QRect(rect.x(), rect.y() + 6, 3, rect.height() - 12), QColor(PIN_COLOR))

        pad = 10
        x = rect.x() + pad + (6 if pinned else 0)
        y = rect.y()
        h = rect.height()

        # right buttons always reserved
        btn_gap = 6
        copy_x = rect.right() - pad - BTN_SIZE
        pin_x = copy_x - btn_gap - BTN_SIZE
        actions_w = (rect.right() - pin_x) + pad

        # icon / thumb
        icon_sz = 28
        if item_type == "image":
            thumb = _load_thumbnail(image_path, icon_sz)
            if thumb and not thumb.isNull():
                painter.drawPixmap(x, y + (h - thumb.height()) // 2, thumb)
            else:
                painter.setPen(QColor(FG_DIM))
                painter.drawText(
                    QRect(x, y, icon_sz, h),
                    Qt.AlignmentFlag.AlignCenter,
                    "IMG",
                )
        else:
            painter.setPen(QColor(ACCENT))
            f = QFont("Segoe UI", 11)
            painter.setFont(f)
            painter.drawText(
                QRect(x, y, icon_sz, h),
                Qt.AlignmentFlag.AlignCenter,
                "Aa",
            )

        text_x = x + icon_sz + 8
        text_w = max(40, pin_x - text_x - 8)

        # primary line (truncated)
        display = text if item_type == "text" else "[Image]"
        if not display:
            display = "[empty]"
        display = display.replace("\n", " ").replace("\r", " ").strip()
        painter.setPen(QColor(FG))
        painter.setFont(QFont("Segoe UI", 10))
        metrics = painter.fontMetrics()
        elided = metrics.elidedText(display, Qt.TextElideMode.ElideRight, text_w)
        painter.drawText(
            QRect(text_x, y + 6, text_w, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        # timestamp
        ts = (created_at or "").replace("T", "  ")
        painter.setPen(QColor(FG_DIM))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            QRect(text_x, y + 26, text_w, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ts,
        )

        # pin button — always visible; gold when pinned
        pin_rect = QRect(pin_x, y + (h - BTN_SIZE) // 2, BTN_SIZE, BTN_SIZE)
        self.pin_rects[row] = pin_rect
        if pinned:
            painter.setBrush(QBrush(QColor("#4a4020")))
            painter.setPen(QPen(QColor(PIN_COLOR), 1))
        elif hovered or selected:
            painter.setBrush(QBrush(QColor(PIN_BTN)))
            painter.setPen(QPen(QColor(BORDER), 1))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawRoundedRect(pin_rect, 5, 5)
        painter.setPen(QColor(PIN_COLOR if pinned else FG_DIM))
        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold if pinned else QFont.Weight.Normal))
        painter.drawText(pin_rect, Qt.AlignmentFlag.AlignCenter, "★" if pinned else "☆")

        # copy button — two overlapping rectangles (always shown)
        copy_rect = QRect(copy_x, y + (h - BTN_SIZE) // 2, BTN_SIZE, BTN_SIZE)
        self.copy_rects[row] = copy_rect
        if hovered or selected:
            painter.setBrush(QBrush(QColor(COPY_BTN)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(copy_rect, 5, 5)
            line = QColor("#ffffff")
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(BORDER), 1))
            painter.drawRoundedRect(copy_rect, 5, 5)
            line = QColor(FG_DIM)
        painter.setPen(QPen(line, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r1 = QRectF(copy_rect.x() + 6, copy_rect.y() + 6, 11, 11)
        r2 = QRectF(copy_rect.x() + 10, copy_rect.y() + 10, 11, 11)
        painter.drawRoundedRect(r1, 1.5, 1.5)
        if hovered or selected:
            painter.setBrush(QBrush(QColor(COPY_BTN)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(r2, 1.5, 1.5)
            painter.setPen(QPen(line, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r2, 1.5, 1.5)

    def sizeHint(self, option, index):
        return QSize(0, ROW_H)


# ---------- sidebar ----------
class FolderSidebar(QWidget):
    folder_selected = pyqtSignal(object)  # None=All, -1=Uncategorized, int=folder id
    create_folder_requested = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setFixedWidth(SIDEBAR_W)
        self.setObjectName("sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.list = QListWidget()
        self.list.setObjectName("folderList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSpacing(0)
        self.list.itemClicked.connect(self._on_click)
        layout.addWidget(self.list, 1)

        add_btn = QToolButton()
        add_btn.setObjectName("addFolderBtn")
        add_btn.setText("+ New folder")
        add_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self.create_folder_requested.emit)
        layout.addWidget(add_btn)

        self.refresh()
        self.list.setCurrentRow(0)

    def refresh(self, select_fid=None):
        prev = select_fid
        if prev is None and self.list.currentItem():
            prev = self.list.currentItem().data(Qt.ItemDataRole.UserRole)

        self.list.blockSignals(True)
        self.list.clear()

        all_item = QListWidgetItem("All")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.list.addItem(all_item)

        uncat = QListWidgetItem("Uncategorized")
        uncat.setData(Qt.ItemDataRole.UserRole, -1)
        self.list.addItem(uncat)

        for fid, name in self.db.get_folders():
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, fid)
            self.list.addItem(it)

        # restore selection
        chosen = 0
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == prev:
                chosen = i
                break
        self.list.setCurrentRow(chosen)
        self.list.blockSignals(False)

    def _on_click(self, item):
        self.folder_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def current_folder_id(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


# ---------- main window ----------
class ClipboardWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.items = []
        self._selected_folder = None
        self._keep_open = False
        self._setup_ui()
        self._setup_shortcuts()
        self._apply_style()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WINDOW_W, WINDOW_H)

        self.container = QFrame(self)
        self.container.setObjectName("mainContainer")
        # tight outer margin (was 8)
        self.container.setGeometry(4, 4, WINDOW_W - 8, WINDOW_H - 8)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # title bar
        title = QFrame()
        title.setObjectName("titleBar")
        title.setFixedHeight(32)
        tl = QHBoxLayout(title)
        tl.setContentsMargins(10, 0, 4, 0)
        tl.setSpacing(4)

        title_lbl = QLabel("Clipboard")
        title_lbl.setObjectName("titleText")
        tl.addWidget(title_lbl)
        tl.addStretch()

        self.keep_btn = QToolButton(self)
        self.keep_btn.setObjectName("toolBtn")
        self.keep_btn.setText("Keep open")
        self.keep_btn.setCheckable(True)
        self.keep_btn.setToolTip("Don't hide window after copy")
        self.keep_btn.toggled.connect(lambda v: setattr(self, "_keep_open", v))
        self.keep_btn.hide()

        self.cmd_btn = QToolButton(self)
        self.cmd_btn.setObjectName("toolBtn")
        self.cmd_btn.setText("Cmd")
        self.cmd_btn.setCheckable(True)
        self.cmd_btn.setToolTip("Type a command")
        self.cmd_btn.toggled.connect(self._toggle_cmd_bar)
        self.cmd_btn.hide()

        help_btn = QToolButton()
        help_btn.setObjectName("helpBtn")
        help_btn.setText("?")
        help_btn.setToolTip("Help")
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.clicked.connect(
            lambda: self.search_input.setText("type clipboard in terminal")
        )
        tl.addWidget(help_btn)

        close_btn = QToolButton()
        close_btn.setObjectName("closeBtn")
        close_btn.setText("✕")
        close_btn.clicked.connect(self.hide)
        tl.addWidget(close_btn)
        root.addWidget(title)

        # search — tight padding
        search_wrap = QFrame()
        search_wrap.setObjectName("searchFrame")
        sl = QHBoxLayout(search_wrap)
        sl.setContentsMargins(8, 2, 8, 4)
        sl.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search…")
        self.search_input.setFixedHeight(28)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search)
        sl.addWidget(self.search_input)

        self.cmd_input = QLineEdit()
        self.cmd_input.setObjectName("cmdInput")
        self.cmd_input.setPlaceholderText("open · close · stop · status · help")
        self.cmd_input.setFixedHeight(28)
        self.cmd_input.setClearButtonEnabled(True)
        self.cmd_input.hide()
        self.cmd_input.returnPressed.connect(self._run_command)
        sl.addWidget(self.cmd_input)
        root.addWidget(search_wrap)

        # body: sidebar + list
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(1)
        split.setObjectName("mainSplit")

        self.sidebar = FolderSidebar(self.db)
        self.sidebar.folder_selected.connect(self._on_folder_selected)
        self.sidebar.create_folder_requested.connect(self._add_folder_dialog)
        self.sidebar.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar.list.customContextMenuRequested.connect(self._folder_context_menu)
        split.addWidget(self.sidebar)

        list_box = QFrame()
        list_box.setObjectName("listContainer")
        ll = QVBoxLayout(list_box)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("clipList")
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setUniformItemSizes(True)
        self.delegate = ClipDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self.delegate)
        self.list_widget.viewport().installEventFilter(self)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._list_context_menu)
        ll.addWidget(self.list_widget)

        hint = QLabel("↑↓  Enter copy  ·  Ctrl+P pin  ·  Del  ·  Esc  ·  right-click for folder")
        hint.setObjectName("hintText")
        hint.setFixedHeight(22)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(hint)

        split.addWidget(list_box)
        split.setSizes([SIDEBAR_W, WINDOW_W - SIDEBAR_W])
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        root.addWidget(split, 1)

        self._drag_pos = None
        title.mousePressEvent = self._title_press
        title.mouseMoveEvent = self._title_move

    def _title_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def _title_move(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, self._copy_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, self._copy_selected)
        QShortcut(QKeySequence("Ctrl+C"), self, self._copy_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.hide)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, self._move_next)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, self._move_prev)
        QShortcut(QKeySequence("Ctrl+P"), self, self._toggle_pin_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._delete_selected)
        QShortcut(QKeySequence("Ctrl+N"), self, self._add_folder_dialog)
        QShortcut(QKeySequence("Ctrl+;"), self, lambda: self.cmd_btn.toggle())
        for i in range(1, 10):
            QShortcut(QKeySequence(str(i)), self, lambda n=i: self._copy_by_index(n - 1))

    def _apply_style(self):
        self.setStyleSheet(f"""
            #mainContainer {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            #titleBar {{
                background: {BG};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            #titleText {{
                color: {FG};
                font: 600 12px "Segoe UI";
            }}
            #toolBtn {{
                color: {FG_DIM};
                background: transparent;
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 2px 8px;
                font: 10px "Segoe UI";
            }}
            #toolBtn:hover {{ background: {BG_HOVER}; color: {FG}; }}
            #toolBtn:checked {{
                color: {ACCENT};
                border-color: {ACCENT};
            }}
            #helpBtn {{
                color: {FG_DIM};
                background: transparent;
                border: 1px solid {BORDER};
                border-radius: 11px;
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
                padding: 0;
                font: 600 12px "Segoe UI";
            }}
            #helpBtn:hover {{ background: {BG_HOVER}; color: {FG}; border-color: {ACCENT}; }}
            #closeBtn {{
                color: {FG_DIM};
                background: transparent;
                border: none;
                font-size: 12px;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            #closeBtn:hover {{ background: #a83232; color: white; }}
            #searchFrame {{
                background: {BG};
            }}
            #searchInput {{
                background: {BG_ALT};
                color: {FG};
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 2px 8px;
                font: 11px "Segoe UI";
                selection-background-color: {ACCENT};
            }}
            #searchInput:focus {{ border-color: {ACCENT}; }}
            #cmdInput {{
                background: {BG_ALT};
                color: {ACCENT};
                border: 1px solid {ACCENT};
                border-radius: 5px;
                padding: 2px 8px;
                font: 11px "Consolas", "Segoe UI";
                selection-background-color: {ACCENT};
            }}
            #cmdInput:focus {{ border-color: {ACCENT}; }}
            #sidebar {{
                background: {SIDEBAR_BG};
                border-right: 1px solid {BORDER};
            }}
            #folderList {{
                background: {SIDEBAR_BG};
                color: {FG};
                border: none;
                outline: none;
                font: 11px "Segoe UI";
            }}
            #folderList::item {{
                padding: 7px 10px;
                border-radius: 0;
            }}
            #folderList::item:selected {{
                background: {BG_SELECTED};
                color: {FG};
            }}
            #folderList::item:hover {{
                background: {BG_HOVER};
            }}
            #addFolderBtn {{
                background: {BG};
                color: {ACCENT};
                border: none;
                border-top: 1px solid {BORDER};
                padding: 8px;
                font: 11px "Segoe UI";
                text-align: left;
            }}
            #addFolderBtn:hover {{ background: {BG_HOVER}; }}
            #listContainer, #clipList {{
                background: {SURFACE};
                border: none;
                outline: none;
            }}
            #hintText {{
                background: {BG};
                color: {FG_DIM};
                font: 9px "Segoe UI";
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QSplitter::handle {{ background: {BORDER}; }}
            QScrollBar:vertical {{
                background: transparent;
                width: 5px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                border-radius: 2px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QMenu {{
                background: {BG};
                color: {FG};
                border: 1px solid {BORDER};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 18px;
                border-radius: 3px;
            }}
            QMenu::item:selected {{ background: {BG_HOVER}; }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER};
                margin: 4px 8px;
            }}
        """)

    def show_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        pos = QCursor.pos()
        x = pos.x() - WINDOW_W // 2
        y = pos.y() - 10
        x = max(screen.left(), min(x, screen.right() - WINDOW_W))
        y = max(screen.top(), min(y, screen.bottom() - WINDOW_H))
        self.move(x, y)
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def refresh(self):
        query = self.search_input.text().strip()
        self.items = self.db.search(query, self._selected_folder)
        self._rebuild_list()

    def _rebuild_list(self):
        prev_id = None
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items):
            prev_id = self.items[row][0]

        self.list_widget.clear()
        self.delegate.copy_rects.clear()
        self.delegate.pin_rects.clear()

        if not self.items:
            empty = QListWidgetItem()
            empty.setData(Qt.ItemDataRole.UserRole, None)
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(empty)
            return

        select_row = 0
        for i, row_data in enumerate(self.items[:150]):
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, row_data)
            it.setSizeHint(QSize(0, ROW_H))
            self.list_widget.addItem(it)
            if prev_id is not None and row_data[0] == prev_id:
                select_row = i

        self.list_widget.setCurrentRow(select_row)

    def _on_search(self):
        self.refresh()

    def _toggle_cmd_bar(self, on):
        self.cmd_input.setVisible(on)
        self.search_input.setVisible(not on)
        if on:
            self.cmd_input.clear()
            self.cmd_input.setPlaceholderText("open · close · stop · status · help")
            self.cmd_input.setFocus()
        else:
            self.search_input.setFocus()

    def _run_command(self):
        raw = self.cmd_input.text().strip().lower()
        if not raw:
            return
        cmd = " ".join(raw.replace("_", " ").split())
        aliases = {
            "open": "open",
            "close": "close",
            "stop": "stop",
            "status": "status",
            "help": "help",
            "quit": "stop",
            "hide": "close",
            "show": "open",
        }
        action = aliases.get(cmd)

        if action == "stop":
            QApplication.quit()
            return
        if action == "close":
            self.cmd_btn.setChecked(False)
            self.hide()
            return
        if action == "open":
            self.cmd_btn.setChecked(False)
            self.show_window()
            return
        if action == "status":
            n = len(self.items)
            self.cmd_input.setPlaceholderText(f"Running · {n} items · {HOTKEY}")
            self.cmd_input.clear()
            return
        if action == "help":
            self.cmd_input.setPlaceholderText("open · close · stop · status · help")
            self.cmd_input.clear()
            return
        self.cmd_input.setPlaceholderText("open · close · stop · status · help")
        self.cmd_input.clear()

    def _on_folder_selected(self, fid):
        self._selected_folder = fid
        self.refresh()

    def _add_folder_dialog(self):
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        if not ok or not name.strip():
            return
        fid = self.db.add_folder(name.strip())
        if fid is None:
            QMessageBox.warning(self, "Folder", f"'{name.strip()}' already exists.")
            return
        self.sidebar.refresh(select_fid=fid)
        self._selected_folder = fid
        self.refresh()

    def _rename_folder(self, fid):
        folders = dict(self.db.get_folders())
        current = folders.get(fid, "")
        name, ok = QInputDialog.getText(self, "Rename folder", "New name:", text=current)
        if not ok or not name.strip():
            return
        if not self.db.rename_folder(fid, name.strip()):
            QMessageBox.warning(self, "Folder", f"'{name.strip()}' already exists.")
            return
        self.sidebar.refresh(select_fid=fid)

    def _delete_folder(self, fid):
        folders = dict(self.db.get_folders())
        name = folders.get(fid, "")
        reply = QMessageBox.question(
            self,
            "Delete folder",
            f'Delete "{name}"?\nItems become Uncategorized.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_folder(fid)
        if self._selected_folder == fid:
            self._selected_folder = None
        self.sidebar.refresh(select_fid=None)
        self.refresh()

    def _folder_context_menu(self, pos):
        item = self.sidebar.list.itemAt(pos)
        if item is None:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid is None or fid == -1:
            return
        menu = QMenu(self)
        ren = menu.addAction("Rename")
        ren.triggered.connect(lambda: self._rename_folder(fid))
        dele = menu.addAction("Delete")
        dele.triggered.connect(lambda: self._delete_folder(fid))
        menu.exec(self.sidebar.list.viewport().mapToGlobal(pos))

    def _list_context_menu(self, pos):
        idx = self.list_widget.indexAt(pos)
        if not idx.isValid() or idx.row() >= len(self.items):
            return
        self.list_widget.setCurrentRow(idx.row())
        self._show_item_menu(idx.row(), self.list_widget.viewport().mapToGlobal(pos))

    def _show_item_menu(self, idx, global_pos):
        item = self.items[idx]
        item_id, text, created_at, pinned, item_type, image_path, folder_id = item

        menu = QMenu(self)
        copy_a = menu.addAction("Copy")
        copy_a.triggered.connect(lambda: self._copy_item(idx))

        pin_a = menu.addAction("Unpin" if pinned else "Pin")
        pin_a.triggered.connect(lambda: self._pin_item(item_id))

        folder_menu = menu.addMenu("Add to folder")
        none_a = folder_menu.addAction("Uncategorized")
        none_a.triggered.connect(lambda: self._move_to_folder(item_id, -1))
        folders = self.db.get_folders()
        if folders:
            folder_menu.addSeparator()
            for fid, name in folders:
                mark = " ✓" if folder_id == fid else ""
                a = folder_menu.addAction(name + mark)
                a.triggered.connect(lambda checked=False, f=fid: self._move_to_folder(item_id, f))
        folder_menu.addSeparator()
        new_f = folder_menu.addAction("New folder…")
        new_f.triggered.connect(lambda: self._add_folder_then_move(item_id))

        menu.addSeparator()
        del_a = menu.addAction("Delete")
        del_a.triggered.connect(lambda: self._delete_item(item_id))
        menu.exec(global_pos)

    def _add_folder_then_move(self, item_id):
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        if not ok or not name.strip():
            return
        fid = self.db.add_folder(name.strip())
        if fid is None:
            QMessageBox.warning(self, "Folder", f"'{name.strip()}' already exists.")
            return
        self.db.set_folder(item_id, fid)
        self.sidebar.refresh(select_fid=fid)
        self._selected_folder = fid
        self.refresh()

    def _move_to_folder(self, item_id, fid):
        self.db.set_folder(item_id, fid)
        self.refresh()

    def _copy_selected(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items):
            self._copy_item(row)

    def _copy_by_index(self, idx):
        if 0 <= idx < len(self.items):
            self._copy_item(idx)

    def _copy_item(self, idx):
        if not (0 <= idx < len(self.items)):
            return
        item_id, text, created_at, pinned, item_type, image_path, folder_id = self.items[idx]
        clipboard = QApplication.clipboard()
        if item_type == "image" and image_path and os.path.exists(image_path):
            qimg = QImage(image_path)
            if not qimg.isNull():
                clipboard.setImage(qimg)
            elif text:
                clipboard.setText(text)
        elif text:
            clipboard.setText(text)
        if not self._keep_open:
            self.hide()

    def _toggle_pin_selected(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items):
            self._pin_item(self.items[row][0])

    def _pin_item(self, item_id):
        self.db.toggle_pin(item_id)
        self.refresh()

    def _delete_selected(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items):
            self._delete_item(self.items[row][0])

    def _delete_item(self, item_id):
        self.db.delete(item_id)
        self.refresh()

    def _move_next(self):
        if not self.items:
            return
        r = self.list_widget.currentRow()
        self.list_widget.setCurrentRow(min(len(self.items) - 1, max(0, r) + 1))

    def _move_prev(self):
        if not self.items:
            return
        r = self.list_widget.currentRow()
        self.list_widget.setCurrentRow(max(0, r - 1))

    def eventFilter(self, obj, event):
        if obj is not self.list_widget.viewport():
            return super().eventFilter(obj, event)

        etype = event.type()

        if etype == QEvent.Type.Leave:
            self.delegate.set_hovered(-1)
            self.list_widget.viewport().update()
            return super().eventFilter(obj, event)

        if etype == QEvent.Type.MouseMove:
            pos = event.position().toPoint()
            idx = self.list_widget.indexAt(pos)
            row = idx.row() if idx.isValid() else -1
            if row != self.delegate._hovered_row:
                self.delegate.set_hovered(row)
                self.list_widget.viewport().update()
            return super().eventFilter(obj, event)

        if etype == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            idx = self.list_widget.indexAt(pos)
            if not idx.isValid():
                return super().eventFilter(obj, event)
            row = idx.row()
            if not (0 <= row < len(self.items)):
                return super().eventFilter(obj, event)

            # pin button?
            pin_r = self.delegate.pin_rects.get(row)
            if pin_r is not None and pin_r.contains(pos):
                self.list_widget.setCurrentRow(row)
                self._pin_item(self.items[row][0])
                return True

            # copy button only — body click just selects
            copy_r = self.delegate.copy_rects.get(row)
            if copy_r is not None and copy_r.contains(pos):
                self.list_widget.setCurrentRow(row)
                self._copy_item(row)
                return True

            self.list_widget.setCurrentRow(row)
            return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            if self.sidebar.list.hasFocus():
                self.list_widget.setFocus()
            else:
                self.sidebar.list.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)


# ---------- tray ----------
class TrayIcon(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self.setIcon(self._make_icon())
        self.setToolTip("Clipboard Manager  (Ctrl+B)")

        menu = QMenu()
        show_a = menu.addAction("Show")
        show_a.triggered.connect(self._toggle)
        quit_a = menu.addAction("Quit")
        quit_a.triggered.connect(QApplication.quit)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _make_icon(self):
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(ACCENT)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(10, 8, 44, 48, 8, 8)
        p.setPen(QPen(QColor("#ffffff"), 3))
        p.drawLine(20, 22, 44, 22)
        p.drawLine(20, 32, 44, 32)
        p.drawLine(20, 42, 36, 42)
        p.end()
        return QIcon(pix)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle()

    def _toggle(self):
        if self._window.isVisible():
            self._window.hide()
        else:
            self._window.show_window()


# ---------- external commands (CLI) ----------
def _write_pid():
    os.makedirs(DB_DIR, exist_ok=True)
    try:
        with open(PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def _clear_pid():
    try:
        if os.path.exists(PID_PATH):
            os.remove(PID_PATH)
    except OSError:
        pass
    try:
        if os.path.exists(CMD_PATH):
            os.remove(CMD_PATH)
    except OSError:
        pass


def _poll_external_command(window):
    if not os.path.exists(CMD_PATH):
        return
    try:
        with open(CMD_PATH, "r", encoding="utf-8") as f:
            cmd = f.read().strip().lower()
    except OSError:
        return
    try:
        os.remove(CMD_PATH)
    except OSError:
        pass
    if not cmd:
        return
    if cmd in ("open", "show"):
        window.show_window()
    elif cmd in ("close", "hide"):
        window.hide()
    elif cmd in ("quit", "stop", "exit"):
        QApplication.quit()
    elif cmd == "toggle":
        if window.isVisible():
            window.hide()
        else:
            window.show_window()


# ---------- main ----------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setApplicationName("Clipboard Manager")

    db = ClipboardDB(DB_PATH)
    window = ClipboardWindow(db)

    watcher = ClipboardWatcher(db)
    watcher.item_added.connect(window.refresh)
    watcher.start()

    tray = TrayIcon(window)
    tray.show()

    keyboard.add_hotkey(HOTKEY, lambda: QTimer.singleShot(0, window.show_window))

    _write_pid()
    app.aboutToQuit.connect(_clear_pid)

    cmd_timer = QTimer()
    cmd_timer.timeout.connect(lambda: _poll_external_command(window))
    cmd_timer.start(250)

    code = app.exec()
    watcher.stop()
    watcher.wait(2000)
    _clear_pid()
    sys.exit(code)


if __name__ == "__main__":
    main()
