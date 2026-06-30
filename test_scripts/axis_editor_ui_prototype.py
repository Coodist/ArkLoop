"""Prototype UI for ArkLoop — dual-panel layout matching the Figma reference.

This script renders two connected borderless panels inside a single root window:
1. A "Timelines" list panel in the top-left.
2. An axis timeline panel below it, with its left edge aligned to the list panel.

The visual design follows the provided Figma screenshot as closely as possible:
* Pure black + gray VSCode-like palette.
* Custom title bars with settings gear and min/max/close buttons.
* Left-pointing chevron cells on the timeline, all the same size, with subtle
  drop shadows.
* Pixel-aligned 1 px strokes.
* DPI awareness for crisp rendering on scaled displays.

Controls:
* Drag either panel by its title bar.
* Press Esc or use right-click menu to exit.

Usage:
    .venv\Scripts\python scripts/axis_editor_ui_prototype.py
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from dataclasses import dataclass
from typing import List, Tuple

# -----------------------------------------------------------------------------
# Windows DPI awareness — makes lines and text sharp on scaled displays.
# -----------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Theme
# -----------------------------------------------------------------------------
BG_ROOT = "#000000"
BG_PANEL = "#111214"
BG_SIDEBAR = "#0d0e10"
BG_TIMELINE = "#111214"
BG_TIMELINE_TRACK = "#15171a"
TEXT_PRIMARY = "#d4d4d4"
TEXT_SECONDARY = "#9ca3af"
TEXT_DIM = "#5c6370"
ACCENT_BLUE = "#4a9eff"      # Playhead
ACCENT_RED = "#ff5f57"       # Record / stop
ACCENT_GREEN = "#28c840"     # Play
GRID_LINE = "#1e2023"
RULER_TEXT = "#7d8590"
BLOCK_FILL = "#4a4d52"
BLOCK_SHADOW = "#000000"
BORDER_PANEL = "#2d2f33"
TITLE_BAR_BG = "#0f1012"
TITLE_BTN_HOVER = "#1c1e21"
TITLE_BTN_ACTIVE = "#c42b1c"

# -----------------------------------------------------------------------------
# Layout
# -----------------------------------------------------------------------------
LIST_PANEL = {"w": 240, "h": 360, "x": 50, "y": 50}
AXIS_PANEL = {"w": 960, "h": 280, "x": 50, "y": 430}
TITLE_BAR_HEIGHT = 32

# -----------------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------------
@dataclass
class TimelineItem:
    name: str
    selected: bool = False


@dataclass
class AxisBlock:
    row: str  # "deploy" | "skill" | "retreat"
    time_s: float
    selected: bool = False


# -----------------------------------------------------------------------------
# Sample data
# -----------------------------------------------------------------------------
TIMELINES = [
    TimelineItem("TimeLine1", selected=True),
    TimelineItem("TimeLine2"),
    TimelineItem("TimeLine3"),
]

AXIS_BLOCKS: List[AxisBlock] = [
    AxisBlock("deploy", 5.0),
    AxisBlock("skill", 12.0),
    AxisBlock("retreat", 20.0),
]

AXIS_DURATION = 30.0  # seconds

# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------
def px(x: float) -> float:
    """Pixel-align a coordinate for sharp 1 px strokes."""
    return float(x) + 0.5


def draw_crisp_line(
    canvas: tk.Canvas,
    x1: float, y1: float, x2: float, y2: float,
    fill: str, width: float = 1.0,
) -> int:
    return canvas.create_line(
        px(x1), px(y1), px(x2), px(y2),
        fill=fill, width=width, smooth=False,
    )


def draw_left_chevron(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    width: float,
    height: float,
    point: float,
    fill: str,
    outline: str,
    outline_width: float = 1.0,
) -> int:
    """Draw a left-pointing chevron/pentagon."""
    half_w = width / 2
    half_h = height / 2
    points = [
        px(cx - half_w - point), px(cy),          # left tip
        px(cx - half_w), px(cy - half_h),         # top-left diagonal
        px(cx + half_w), px(cy - half_h),         # top-right
        px(cx + half_w), px(cy + half_h),         # bottom-right
        px(cx - half_w), px(cy + half_h),         # bottom-left diagonal
    ]
    return canvas.create_polygon(
        points, fill=fill, outline=outline, width=outline_width, smooth=False
    )


def draw_shadow_chevron(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    width: float,
    height: float,
    point: float,
    fill: str,
    outline: str,
    shadow_color: str = BLOCK_SHADOW,
    shadow_offset: Tuple[int, int] = (2, 2),
) -> None:
    """Draw a chevron with a subtle drop shadow behind it."""
    sx, sy = shadow_offset
    # Shadow
    draw_left_chevron(
        canvas, cx + sx, cy + sy,
        width, height, point,
        fill=shadow_color, outline=shadow_color, outline_width=1.0
    )
    # Main shape
    draw_left_chevron(
        canvas, cx, cy,
        width, height, point,
        fill=fill, outline=outline, outline_width=1.0
    )


# -----------------------------------------------------------------------------
# Reusable borderless panel
# -----------------------------------------------------------------------------
class BorderlessPanel:
    """A panel with a custom title bar and VSCode-like border."""

    def __init__(
        self,
        parent: tk.Widget,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str = "",
        show_settings: bool = False,
    ) -> None:
        self.parent = parent
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title

        self.frame = tk.Frame(
            parent, width=width, height=height,
            bg=BORDER_PANEL, highlightthickness=0,
        )
        self.frame.place(x=x, y=y)
        self.frame.pack_propagate(False)

        self._drag_data = {"x": 0, "y": 0, "dragging": False}

        self.content = tk.Frame(
            self.frame, bg=BG_PANEL, highlightthickness=0,
        )
        self.content.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.content.pack_propagate(False)

        self._build_title_bar(show_settings)

    def _build_title_bar(self, show_settings: bool) -> None:
        self.title_bar = tk.Frame(
            self.content, height=TITLE_BAR_HEIGHT,
            bg=TITLE_BAR_BG, highlightthickness=0,
        )
        self.title_bar.pack(side=tk.TOP, fill=tk.X)
        self.title_bar.pack_propagate(False)

        # Settings gear icon
        if show_settings:
            gear = tk.Canvas(
                self.title_bar, width=20, height=20,
                bg=TITLE_BAR_BG, highlightthickness=0,
            )
            gear.pack(side=tk.LEFT, padx=(10, 0), pady=6)
            # Simple 8-tooth gear drawn as a circle with small rectangles
            cx, cy = 10, 10
            r = 5
            gear.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=TEXT_SECONDARY, width=1.5, fill=""
            )
            for angle in range(0, 360, 45):
                import math
                rad = math.radians(angle)
                x1 = cx + (r - 1) * math.cos(rad)
                y1 = cy + (r - 1) * math.sin(rad)
                x2 = cx + (r + 2) * math.cos(rad)
                y2 = cy + (r + 2) * math.sin(rad)
                gear.create_line(x1, y1, x2, y2, fill=TEXT_SECONDARY, width=1.5)

        # Spacer to push controls right
        spacer = tk.Label(self.title_bar, bg=TITLE_BAR_BG)
        spacer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Window control buttons
        for symbol, cmd, active_color in (
            ("—", self._minimize, None),
            ("□", self._toggle_maximize, None),
            ("×", self._close, TITLE_BTN_ACTIVE),
        ):
            btn = tk.Label(
                self.title_bar, text=symbol,
                fg=TEXT_SECONDARY, bg=TITLE_BAR_BG,
                font=("Segoe UI", 10), width=3, anchor=tk.CENTER,
            )
            btn.pack(side=tk.RIGHT, fill=tk.Y)
            btn.bind(
                "<Enter>",
                lambda _e, b=btn, ac=active_color: b.configure(
                    bg=ac if ac else TITLE_BTN_HOVER,
                    fg=TEXT_PRIMARY if ac else TEXT_SECONDARY,
                ),
            )
            btn.bind(
                "<Leave>",
                lambda _e, b=btn: b.configure(bg=TITLE_BAR_BG, fg=TEXT_SECONDARY),
            )
            btn.bind("<ButtonPress-1>", lambda _e, c=cmd: c())

        # Dragging
        self.title_bar.bind("<ButtonPress-1>", self._on_drag_start)
        self.title_bar.bind("<B1-Motion>", self._on_drag)
        self.title_bar.bind("<ButtonRelease-1>", self._on_drag_stop)

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_data["x"] = event.x_root - self.frame.winfo_x()
        self._drag_data["y"] = event.y_root - self.frame.winfo_y()
        self._drag_data["dragging"] = True

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag_data["dragging"]:
            return
        new_x = event.x_root - self._drag_data["x"]
        new_y = event.y_root - self._drag_data["y"]
        self.frame.place(x=new_x, y=new_y)

    def _on_drag_stop(self, _event: tk.Event) -> None:
        self._drag_data["dragging"] = False

    def _minimize(self) -> None:
        # For a placed frame we cannot truly iconify; just hide.
        self.frame.place_forget()

    def _toggle_maximize(self) -> None:
        # For a prototype, toggle between normal and fill-parent.
        if self.frame.winfo_width() == self.width:
            self.frame.place(x=0, y=0, width=self.parent.winfo_width(),
                             height=self.parent.winfo_height())
        else:
            self.frame.place(x=self.x, y=self.y, width=self.width, height=self.height)

    def _close(self) -> None:
        self.frame.destroy()


# -----------------------------------------------------------------------------
# Main application
# -----------------------------------------------------------------------------
class ArkLoopPrototype:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ArkLoop")
        self.root.configure(bg=BG_ROOT)
        self.root.overrideredirect(True)

        # Total size to hold both panels with some padding.
        total_w = max(LIST_PANEL["x"] + LIST_PANEL["w"], AXIS_PANEL["x"] + AXIS_PANEL["w"]) + 50
        total_h = AXIS_PANEL["y"] + AXIS_PANEL["h"] + 50
        self.root.geometry(f"{total_w}x{total_h}+80+60")

        self._bind_global_controls()

        # Timelines list panel
        self.list_panel = BorderlessPanel(
            self.root,
            x=LIST_PANEL["x"],
            y=LIST_PANEL["y"],
            width=LIST_PANEL["w"],
            height=LIST_PANEL["h"],
            title="",
            show_settings=True,
        )
        self._build_list_content(self.list_panel.content)

        # Axis timeline panel
        self.axis_panel = BorderlessPanel(
            self.root,
            x=AXIS_PANEL["x"],
            y=AXIS_PANEL["y"],
            width=AXIS_PANEL["w"],
            height=AXIS_PANEL["h"],
            title="",
            show_settings=False,
        )
        self._build_axis_content(self.axis_panel.content)

    # ------------------------------------------------------------------
    # Global controls
    # ------------------------------------------------------------------
    def _bind_global_controls(self) -> None:
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event: tk.Event) -> None:
        menu = tk.Menu(
            self.root, tearoff=0, bg=BG_PANEL, fg=TEXT_PRIMARY,
            activebackground="#1f1f1f", activeforeground=TEXT_PRIMARY, bd=0,
        )
        menu.add_command(label="Close", command=self.root.destroy)
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------
    # Timelines list content
    # ------------------------------------------------------------------
    def _build_list_content(self, parent: tk.Frame) -> None:
        # New Timeline button
        new_btn = tk.Frame(
            parent, height=36, bg="#15171a",
            highlightbackground=BORDER_PANEL, highlightthickness=1,
        )
        new_btn.pack(fill=tk.X, padx=10, pady=(10, 0))
        new_btn.pack_propagate(False)

        tk.Label(
            new_btn, text="+", fg=TEXT_SECONDARY, bg="#15171a",
            font=("Segoe UI", 14),
        ).pack(side=tk.LEFT, padx=(12, 6))
        tk.Label(
            new_btn, text="New TimeLine", fg=TEXT_SECONDARY, bg="#15171a",
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT)

        # Section label
        tk.Label(
            parent, text="TimeLines", fg=TEXT_DIM, bg=BG_PANEL,
            font=("Segoe UI", 10),
        ).pack(anchor=tk.W, padx=16, pady=(24, 6))

        # Timeline list
        for item in TIMELINES:
            row = tk.Frame(parent, height=32, bg=BG_PANEL, highlightthickness=0)
            row.pack(fill=tk.X, padx=10, pady=1)
            row.pack_propagate(False)

            if item.selected:
                row.configure(bg="#1a1c20")
                # Subtle left accent line like the Figma mock-up
                accent = tk.Frame(row, width=2, bg=ACCENT_BLUE)
                accent.pack(side=tk.LEFT, fill=tk.Y)

            lbl = tk.Label(
                row, text=item.name,
                fg=TEXT_PRIMARY if item.selected else TEXT_SECONDARY,
                bg=row["bg"], font=("Segoe UI", 10),
            )
            lbl.pack(side=tk.LEFT, padx=(12, 0))

            # Three-dot menu on the right of the item
            menu_btn = tk.Label(
                row, text="⋯", fg=TEXT_DIM, bg=row["bg"],
                font=("Segoe UI", 12), width=3, anchor=tk.CENTER,
            )
            menu_btn.pack(side=tk.RIGHT, padx=(0, 4))
            menu_btn.bind(
                "<Enter>",
                lambda _e, b=menu_btn: b.configure(fg=TEXT_SECONDARY),
            )
            menu_btn.bind(
                "<Leave>",
                lambda _e, b=menu_btn: b.configure(fg=TEXT_DIM),
            )

    # ------------------------------------------------------------------
    # Axis timeline content
    # ------------------------------------------------------------------
    def _build_axis_content(self, parent: tk.Frame) -> None:
        # Top control bar
        control_bar = tk.Frame(
            parent, height=TITLE_BAR_HEIGHT, bg=TITLE_BAR_BG,
            highlightthickness=0,
        )
        control_bar.pack(side=tk.TOP, fill=tk.X)
        control_bar.pack_propagate(False)

        # Three status/control dots
        for color in (ACCENT_RED, ACCENT_RED, ACCENT_GREEN):
            dot = tk.Canvas(
                control_bar, width=12, height=12,
                bg=TITLE_BAR_BG, highlightthickness=0,
            )
            dot.pack(side=tk.LEFT, padx=(8 if color == ACCENT_RED else 4), pady=10)
            dot.create_oval(2, 2, 10, 10, fill=color, outline="")

        # Timeline canvas
        self.timeline_canvas = tk.Canvas(
            parent, bg=BG_TIMELINE, highlightthickness=0,
        )
        self.timeline_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.timeline_canvas.bind("<Configure>", lambda _e: self._draw_timeline())
        self._draw_timeline()

    def _time_to_x(self, t: float, left: float, right: float) -> float:
        return left + (t / AXIS_DURATION) * (right - left)

    def _format_time(self, t: float) -> str:
        minutes = int(t // 60)
        seconds = int(t % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _draw_timeline(self) -> None:
        c = self.timeline_canvas
        c.delete("all")

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 2 or h < 2:
            c.after(50, self._draw_timeline)
            return

        # Layout inside the axis panel
        left_margin = 80
        right_margin = 16
        top_margin = 36
        bottom_margin = 16
        ruler_y = 16

        left = left_margin
        right = w - right_margin
        track_top = top_margin
        track_height = (h - top_margin - bottom_margin) // 3
        track_gap = 0

        # Ruler baseline
        draw_crisp_line(c, left, ruler_y + 10, right, ruler_y + 10, GRID_LINE)

        # Major ticks and labels every 5 seconds
        for s in range(0, int(AXIS_DURATION) + 1, 5):
            x = self._time_to_x(s, left, right)
            draw_crisp_line(c, x, ruler_y + 4, x, ruler_y + 10, RULER_TEXT)
            c.create_text(
                x, ruler_y - 2, text=self._format_time(s),
                fill=RULER_TEXT, font=("Consolas", 9), anchor=tk.N,
            )
            # Minor ticks
            if s + 5 <= AXIS_DURATION:
                for sub in range(1, 5):
                    sx = self._time_to_x(s + sub, left, right)
                    draw_crisp_line(c, sx, ruler_y + 7, sx, ruler_y + 10, GRID_LINE)

        # Playhead at 00:05
        playhead_x = self._time_to_x(5.0, left, right)
        draw_crisp_line(c, playhead_x, ruler_y + 10, playhead_x, h - bottom_margin, ACCENT_BLUE)
        # Diamond marker at top
        c.create_polygon(
            playhead_x, ruler_y - 6,
            playhead_x + 4, ruler_y - 2,
            playhead_x, ruler_y + 2,
            playhead_x - 4, ruler_y - 2,
            fill=ACCENT_BLUE, outline=ACCENT_BLUE,
        )

        # Row labels and tracks
        rows: List[Tuple[str, str]] = [
            ("部署", "deploy"),
            ("技能", "skill"),
            ("撤退", "retreat"),
        ]

        # Uniform block size
        block_w = 96
        block_h = 34
        point = 12

        for i, (label, key) in enumerate(rows):
            y = track_top + i * (track_height + track_gap)
            center_y = y + track_height // 2

            # Row label
            c.create_text(
                36, center_y, text=label,
                fill=TEXT_SECONDARY, font=("Microsoft YaHei UI", 11),
                anchor=tk.CENTER,
            )

            # Row separator lines
            draw_crisp_line(c, 0, y, w, y, GRID_LINE)
            if i == len(rows) - 1:
                draw_crisp_line(c, 0, y + track_height, w, y + track_height, GRID_LINE)

            # Vertical divider between labels and tracks
            draw_crisp_line(c, left_margin, y, left_margin, y + track_height, GRID_LINE)

            # Blocks
            for block in AXIS_BLOCKS:
                if block.row != key:
                    continue
                cx = self._time_to_x(block.time_s, left, right)
                draw_shadow_chevron(
                    c, cx, center_y,
                    block_w, block_h, point,
                    fill=BLOCK_FILL, outline=BLOCK_FILL,
                    shadow_color=BLOCK_SHADOW,
                    shadow_offset=(2, 2),
                )


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    ArkLoopPrototype(root)
    root.mainloop()


if __name__ == "__main__":
    main()
