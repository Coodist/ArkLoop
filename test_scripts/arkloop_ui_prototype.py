"""ArkLoop UI prototype — directly translated from the Figma SVG reference.

This is a fresh implementation based on ``timeline_prototype_figma_fixed_v2.svg``.
It renders a single 946×666 borderless window using a tkinter Canvas and Pillow
for gradients / soft shadows, so the result stays as close as possible to the
reference image.

Controls:
* Drag the window by the left title bar (top 32 px).
* Click the gear / min / max / close icons in the title bar.
* Press Esc or right-click to close.

Usage:
    .venv\Scripts\python scripts/arkloop_ui_prototype.py
"""

from __future__ import annotations

import ctypes
import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

# -----------------------------------------------------------------------------
# Windows DPI awareness
# -----------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Palette / dimensions extracted from the SVG
# -----------------------------------------------------------------------------
WINDOW_WIDTH = 946
WINDOW_HEIGHT = 666

BG_ROOT = "#0B0F13"
SIDEBAR_TOP = "#10151A"
SIDEBAR_LINE = "#20262D"
SIDEBAR_GRAD_START = (17, 22, 27)
SIDEBAR_GRAD_END = (8, 12, 16)

BTN_NEW_TEXT = "#CFD5DC"
TEXT_MUTED = "#A6ADB5"
TEXT_DIM = "#7F8790"
TEXT_PRIMARY = "#D5D9DE"

ACCENT_BLUE = "#49B8FF"
ACCENT_RED = "#FF3B36"
ACCENT_GREEN = "#35C64A"
PLAYHEAD_FILL = "#4AA3D8"
PLAYHEAD_LINE = "#6FC6FF"

GRID_DARK = "#222A31"
GRID_LIGHT = "#252B32"
TICK_COLOR = "#59616A"
DIVIDER = "#1D232A"
WORKSPACE_BORDER = "#D2D2D2"
WORKSPACE_BG = "#FAFAFA"

TIMELINE_TOP = "#11161B"
TIMELINE_BG_START = (19, 24, 29)
TIMELINE_BG_END = (10, 14, 18)

TRACK_START = (103, 107, 112)
TRACK_END = (77, 81, 86)
TRACK_STROKE = "#777C83"
TRACK_SHADOW = (0, 0, 0, 115)

HIGHLIGHT_LINE = "#303841"

# -----------------------------------------------------------------------------

# Sample data
# -----------------------------------------------------------------------------
@dataclass
class TimelineItem:
    name: str
    selected: bool = False


TIMELINES = [
    TimelineItem("TimeLine1", selected=True),
    TimelineItem("TimeLine2"),
    TimelineItem("TimeLine3"),
]


# -----------------------------------------------------------------------------
# Image helpers (gradients / shadows)
# -----------------------------------------------------------------------------
def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def make_gradient_image(
    width: int,
    height: int,
    start: Tuple[int, int, int],
    end: Tuple[int, int, int],
    angle: float = 45.0,
) -> ImageTk.PhotoImage:
    """Create a diagonal RGB gradient image."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    # Project each pixel onto the diagonal direction, normalized to [0, 1].
    ys, xs = np.mgrid[:height, :width]
    proj = (xs * cos_a + ys * sin_a).astype(np.float32)
    t = (proj - proj.min()) / (proj.max() - proj.min() + 1e-6)

    for i in range(3):
        img[:, :, i] = (start[i] * (1 - t) + end[i] * t).astype(np.uint8)

    return ImageTk.PhotoImage(Image.fromarray(img))


def make_block_shadow(
    width: int,
    height: int,
    point: int,
    offset: Tuple[int, int] = (0, 1),
    blur: float = 1.2,
    opacity: int = 115,
) -> ImageTk.PhotoImage:
    """Render a soft drop shadow for a left-pointing chevron block."""
    pad = 6
    w = width + point + pad * 2
    h = height + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx = w // 2
    cy = h // 2
    half_w = width / 2
    half_h = height / 2
    points = [
        (cx - half_w - point + offset[0], cy + offset[1]),
        (cx - half_w + offset[0], cy - half_h + offset[1]),
        (cx + half_w + offset[0], cy - half_h + offset[1]),
        (cx + half_w + offset[0], cy + half_h + offset[1]),
        (cx - half_w + offset[0], cy + half_h + offset[1]),
    ]
    draw.polygon(points, fill=(0, 0, 0, opacity))
    img = img.filter(ImageFilter.GaussianBlur(radius=blur))
    return ImageTk.PhotoImage(img)


# -----------------------------------------------------------------------------
# Main application
# -----------------------------------------------------------------------------
class ArkLoopPrototype:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ArkLoop")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+80+60")
        self.root.configure(bg=BG_ROOT)
        self.root.overrideredirect(True)

        self._is_maximized = False
        self._normal_geometry = self.root.geometry()
        self._drag_data: dict = {"x": 0, "y": 0, "dragging": False}

        # Keep references to PhotoImages so they are not GC'd.
        self._images: list = []

        self.canvas = tk.Canvas(
            self.root, width=WINDOW_WIDTH, height=WINDOW_HEIGHT,
            bg=BG_ROOT, highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._bind_controls()
        self._draw_ui()

    # ------------------------------------------------------------------
    # Window controls
    # ------------------------------------------------------------------
    def _bind_controls(self) -> None:
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.bind("<Button-3>", self._show_context_menu)

        # Title-bar drag area is the top 32 px of the sidebar.
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_stop)

    def _on_drag_start(self, event: tk.Event) -> None:
        # Only drag if clicking the title bar region.
        if event.y > 32 or event.x > 224:
            return
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()
        self._drag_data["dragging"] = True

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag_data["dragging"]:
            return
        new_x = event.x_root - self._drag_data["x"]
        new_y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_drag_stop(self, _event: tk.Event) -> None:
        self._drag_data["dragging"] = False

    def _minimize(self) -> None:
        self.root.iconify()

    def _toggle_maximize(self) -> None:
        if self._is_maximized:
            self.root.geometry(self._normal_geometry)
            self._is_maximized = False
        else:
            self._normal_geometry = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
            self._is_maximized = True

    def _show_context_menu(self, event: tk.Event) -> None:
        menu = tk.Menu(
            self.root, tearoff=0, bg=SIDEBAR_TOP, fg=TEXT_PRIMARY,
            activebackground="#1f1f1f", activeforeground=TEXT_PRIMARY, bd=0,
        )
        menu.add_command(
            label="Restore" if self._is_maximized else "Maximize",
            command=self._toggle_maximize,
        )
        menu.add_command(label="Minimize", command=self._minimize)
        menu.add_separator()
        menu.add_command(label="Close", command=self.root.destroy)
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_ui(self) -> None:
        c = self.canvas

        # Main background
        c.create_rectangle(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT, fill=BG_ROOT, outline="")

        # --- Sidebar (224×435) -------------------------------------------------
        sidebar_img = make_gradient_image(
            224, 435, SIDEBAR_GRAD_START, SIDEBAR_GRAD_END, angle=45
        )
        self._images.append(sidebar_img)
        c.create_image(0, 0, anchor=tk.NW, image=sidebar_img)

        # Sidebar title bar
        c.create_rectangle(0, 0, 224, 32, fill=SIDEBAR_TOP, outline="")

        # Sidebar right border
        c.create_line(223.5, 0, 223.5, 435, fill=SIDEBAR_LINE, width=1)

        # Title icons
        self._draw_title_icons(c)

        # New TimeLine row
        c.create_line(27, 68, 27, 80, fill=BTN_NEW_TEXT, width=1.3, capstyle=tk.ROUND)
        c.create_line(21, 74, 33, 74, fill=BTN_NEW_TEXT, width=1.3, capstyle=tk.ROUND)
        c.create_text(55, 81, text="new TimeLine", anchor=tk.W, fill=TEXT_PRIMARY,
                      font=("Segoe UI", 12))

        # Divider under new-timeline row
        c.create_line(0, 94.5, 224, 94.5, fill=DIVIDER, width=1)

        # TimeLines label
        c.create_text(18, 121, text="TimeLines", anchor=tk.W, fill=TEXT_MUTED,
                      font=("Segoe UI", 10))

        # Timeline list
        self._draw_timeline_list(c)

        # --- Workspace / canvas area ------------------------------------------
        c.create_rectangle(224, 0, WINDOW_WIDTH, 435, fill=WORKSPACE_BG, outline="")
        # Bottom edge of workspace
        c.create_line(224, 434.5, WINDOW_WIDTH, 434.5, fill=WORKSPACE_BORDER, width=1)

        # --- Bottom timeline area ---------------------------------------------
        timeline_bg_img = make_gradient_image(
            WINDOW_WIDTH, 232, TIMELINE_BG_START, TIMELINE_BG_END, angle=45
        )
        self._images.append(timeline_bg_img)
        c.create_image(0, 434, anchor=tk.NW, image=timeline_bg_img)

        # Timeline top bar
        c.create_rectangle(0, 434, WINDOW_WIDTH, 434 + 43, fill=TIMELINE_TOP, outline="")

        # Top border lines
        c.create_line(0, 434.5, WINDOW_WIDTH, 434.5, fill=GRID_LIGHT, width=1)
        c.create_line(0, 477.5, WINDOW_WIDTH, 477.5, fill=GRID_DARK, width=1)

        # Vertical divider at x=109.5
        c.create_line(109.5, 434, 109.5, WINDOW_HEIGHT, fill=GRID_LIGHT, width=1)

        # Transport controls
        self._draw_transport_controls(c)

        # Ruler
        self._draw_ruler(c)

        # Playhead
        self._draw_playhead(c)

        # Row labels and grid lines
        self._draw_tracks(c)

        # Blocks
        self._draw_blocks(c)

        # Subtle highlight line at the top of timeline area
        c.create_line(0, 434, WINDOW_WIDTH, 434, fill=HIGHLIGHT_LINE, width=1)

        # Very subtle white overlay on workspace
        overlay = Image.new("RGBA", (722, 435), (255, 255, 255, 15))
        overlay_tk = ImageTk.PhotoImage(overlay)
        self._images.append(overlay_tk)
        c.create_image(224, 0, anchor=tk.NW, image=overlay_tk)

    def _draw_title_icons(self, c: tk.Canvas) -> None:
        # Gear icon
        cx, cy = 27, 25
        r = 6
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#ADB4BC", width=1.3)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1 = cx + (r - 1) * math.cos(rad)
            y1 = cy + (r - 1) * math.sin(rad)
            x2 = cx + (r + 2) * math.cos(rad)
            y2 = cy + (r + 2) * math.sin(rad)
            c.create_line(x1, y1, x2, y2, fill="#ADB4BC", width=1.1)

        # Minimize
        c.create_line(121, 27.5, 132, 27.5, fill="#A4ABB3", width=1.2)
        # Maximize
        c.create_rectangle(161, 21, 170, 30, outline="#A4ABB3", width=1.1)
        # Close
        c.create_line(196, 20, 206, 30, fill="#A4ABB3", width=1.2)
        c.create_line(206, 20, 196, 30, fill="#A4ABB3", width=1.2)

    def _draw_timeline_list(self, c: tk.Canvas) -> None:
        for i, item in enumerate(TIMELINES):
            y = 135 + i * 45
            if item.selected:
                # Rounded rect background
                self._rounded_rect(c, 8, y, 207, 35, 2, fill="#2A313A", outline="")
                # Left accent bar
                c.create_rectangle(7, y, 9, y + 35, fill=ACCENT_BLUE, outline="")
                fill = TEXT_PRIMARY
            else:
                fill = TEXT_MUTED
            c.create_text(18, y + 23, text=item.name, anchor=tk.W, fill=fill,
                          font=("Segoe UI", 11))

    def _draw_transport_controls(self, c: tk.Canvas) -> None:
        # Record circle
        c.create_oval(20 - 6, 456 - 6, 20 + 6, 456 + 6, fill=ACCENT_RED, outline="")
        # Stop square
        c.create_rectangle(48, 451, 48 + 11, 451 + 11, fill=ACCENT_RED, outline="")
        # Play triangle
        c.create_polygon(82, 449, 94, 456, 82, 463, fill=ACCENT_GREEN, outline="")

    def _draw_ruler(self, c: tk.Canvas) -> None:
        labels = [
            (124, "00:00"), (203, "00:05"), (295, "00:10"),
            (390, "00:15"), (486, "00:20"), (598, "00:25"),
            (901, "00:30"), (718, "3:20"),
        ]
        for x, text in labels:
            c.create_text(x, 456, text=text, anchor=tk.N, fill=TEXT_DIM,
                          font=("Consolas", 10))

        # Small ticks (from SVG)
        tick_data = [
            (118, 468, 477, True), (136, 471, 477, False), (155, 471, 477, False),
            (174, 468, 477, True), (193, 471, 477, False), (211, 464, 477, True),
            (231, 471, 477, False), (249, 471, 477, False), (268, 468, 477, True),
            (287, 471, 477, False), (306, 464, 477, True), (325, 471, 477, False),
            (344, 471, 477, False), (363, 468, 477, True), (382, 471, 477, False),
            (401, 464, 477, True), (420, 471, 477, False), (439, 471, 477, False),
            (458, 468, 477, True), (477, 471, 477, False), (496, 464, 477, True),
            (515, 471, 477, False), (534, 471, 477, False), (553, 468, 477, True),
            (572, 471, 477, False), (591, 464, 477, True), (610, 471, 477, False),
            (629, 471, 477, False), (648, 468, 477, True), (667, 471, 477, False),
            (686, 464, 477, True), (705, 471, 477, False), (724, 471, 477, False),
            (743, 468, 477, True), (762, 471, 477, False), (781, 464, 477, True),
            (800, 471, 477, False), (819, 471, 477, False), (838, 468, 477, True),
            (857, 471, 477, False), (876, 464, 477, True), (895, 471, 477, False),
            (914, 471, 477, False), (933, 468, 477, True),
        ]
        for x, y1, y2, major in tick_data:
            c.create_line(x, y1, x, y2, fill=TICK_COLOR, width=1)

    def _draw_playhead(self, c: tk.Canvas) -> None:
        # Diamond marker
        c.create_polygon(
            211, 462, 216, 467, 211, 472, 206, 467,
            fill=PLAYHEAD_FILL, outline=PLAYHEAD_FILL
        )
        # Vertical line
        c.create_line(211, 472, 211, WINDOW_HEIGHT, fill=PLAYHEAD_LINE,
                      width=1.1)

    def _draw_tracks(self, c: tk.Canvas) -> None:
        # Row labels
        labels = [("部署", 511), ("技能", 578), ("撤退", 646)]
        for text, y in labels:
            c.create_text(18, y, text=text, anchor=tk.W, fill=TEXT_MUTED,
                          font=("Microsoft YaHei UI", 11, "bold"))

        # Full-width separator lines
        for y in (541, 607, 665):
            c.create_line(0, y, WINDOW_WIDTH, y, fill=GRID_DARK, width=1)

        # Partial separator lines from x=110
        for y in (541, 607):
            c.create_line(110, y, WINDOW_WIDTH, y, fill=GRID_DARK, width=1)

    def _draw_blocks(self, c: tk.Canvas) -> None:
        # All blocks share the same body width / height / point length.
        body_w = 94
        height = 40
        point = 22

        blocks = [
            # (center_x, center_y)
            (184, 509),   # deploy (tip at 137)
            (287, 574.5), # skill (tip at 229)
            (385, 639.5), # retreat (tip at 327)
        ]

        for cx, cy in blocks:
            self._draw_block(c, cx, cy, body_w, height, point)

    def _draw_block(
        self,
        c: tk.Canvas,
        cx: float,
        cy: float,
        width: int,
        height: int,
        point: int,
    ) -> None:
        half_w = width / 2
        half_h = height / 2

        # Soft shadow image
        shadow_img = make_block_shadow(width, height, point)
        self._images.append(shadow_img)
        c.create_image(cx, cy, anchor=tk.CENTER, image=shadow_img)

        # Main gradient fill
        gradient = make_gradient_image(
            int(width + point + 4), height, TRACK_START, TRACK_END, angle=45
        )
        self._images.append(gradient)
        # Clip the gradient to the chevron shape by drawing the polygon over it.
        # We place the gradient image centered, then draw the polygon outline.
        c.create_image(cx, cy, anchor=tk.CENTER, image=gradient)

        points = [
            cx - half_w - point, cy,
            cx - half_w, cy - half_h,
            cx + half_w, cy - half_h,
            cx + half_w, cy + half_h,
            cx - half_w, cy + half_h,
        ]
        c.create_polygon(points, fill="", outline=TRACK_STROKE, width=0.8, smooth=False)

    def _rounded_rect(
        self,
        c: tk.Canvas,
        x: int,
        y: int,
        w: int,
        h: int,
        r: int,
        fill: str,
        outline: str = "",
    ) -> None:
        """Draw a rounded rectangle."""
        c.create_rectangle(x + r, y, x + w - r, y + h, fill=fill, outline=fill)
        c.create_rectangle(x, y + r, x + w, y + h - r, fill=fill, outline=fill)
        c.create_oval(x, y, x + 2 * r, y + 2 * r, fill=fill, outline=fill)
        c.create_oval(x + w - 2 * r, y, x + w, y + 2 * r, fill=fill, outline=fill)
        c.create_oval(x, y + h - 2 * r, x + 2 * r, y + h, fill=fill, outline=fill)
        c.create_oval(x + w - 2 * r, y + h - 2 * r, x + w, y + h, fill=fill,
                      outline=fill)


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    ArkLoopPrototype(root)
    root.mainloop()


if __name__ == "__main__":
    main()
