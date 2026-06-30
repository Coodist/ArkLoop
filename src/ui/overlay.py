"""Floating overlay window adapted from ArknightsCostBarRuler.

Displays the current cost bar tick in a compact, dark, always-on-top window.
Right-click anywhere on the overlay to access the context menu.
"""

import logging
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import Menu as tkMenu
from tkinter import font as tkFont
from typing import Callable, Dict, Optional

import ttkbootstrap as ttk
from PIL import Image, ImageTk

from src.config import ImageProcessingConfig as imgconfig
from src.frame.calibration import find_cost_bar_roi
from src.logger import logger

__all__ = ["OverlayWindow"]


FRAMES_PER_SECOND = 30
VERSION = "prts-plus"


def _resource_path(relative_path: str) -> str:
    """Resolve a path relative to the project resource directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, relative_path)


class OverlayWindow:
    def __init__(
        self,
        ui_queue: queue.Queue,
        master_callback: Callable[[Dict], None],
    ):
        logger.info("Initializing OverlayWindow...")
        self.root: Optional[ttk.Window] = None
        self.master_callback = master_callback
        self.ui_queue = ui_queue

        self.current_display_mode = "0_to_n-1"
        self.current_cycle_total_frames = 0
        self.active_profile_filename: Optional[str] = None

        self.fonts: Dict[str, tkFont.Font] = {}
        self.sizes: Dict[str, int] = {}
        self.icons: Dict[str, ImageTk.PhotoImage] = {}
        self._drag_data = {"x": 0, "y": 0}
        self._initial_state: Optional[Dict] = None

    def set_initial_state(self, state: str, display_total: str, active_profile: str,
                          display_mode: str = "0_to_n-1") -> None:
        """Set the state to apply once the window is ready.

        This avoids relying on the ui_queue, which can drop messages before
        the overlay starts processing it.
        """
        self._initial_state = {
            "type": "state_change",
            "state": state,
            "display_total": display_total,
            "active_profile": active_profile,
            "display_mode": display_mode,
        }

    def run(self) -> None:
        logger.info("OverlayWindow.run() - creating root window.")
        self.root = ttk.Window(themename="darkly")
        logger.info("Root window created.")

        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.95)
        self.root.config(bg="#3a3a3a")
        logger.info("Root window attributes set.")

        self._load_icons()
        self._create_widgets()

        std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
        self.setup_geometry(std_w, std_h)

        # Apply any initial state set before run() was called.
        if self._initial_state is not None:
            self._apply_state_change(self._initial_state)
            self._initial_state = None

        self._process_ui_queue()

        logger.info("Entering Tkinter mainloop...")
        self.root.mainloop()

    def _create_widgets(self) -> None:
        logger.debug("Creating overlay widgets...")
        overlay_bg = "#3a3a3a"
        style = ttk.Style()
        style.configure("Overlay.TFrame", background=overlay_bg)
        style.configure("Overlay.TLabel", background=overlay_bg, foreground="white")
        style.configure("Overlay.Total.TLabel", background=overlay_bg, foreground="gray60")
        style.configure("Overlay.Timer.TLabel", background=overlay_bg, foreground="gray60")
        style.configure(
            "Overlay.TButton",
            background=overlay_bg,
            borderwidth=0,
            highlightthickness=0,
            padding=0,
        )
        style.map("Overlay.TButton", background=[("active", "gray40")])

        self.container = ttk.Frame(self.root, style="Overlay.TFrame")
        self.container.pack(expand=True, fill="both")

        self.left_frame = ttk.Frame(self.container, style="Overlay.TFrame")
        self.left_frame.place(relx=0, rely=0, relwidth=0.33, relheight=1.0)

        self.icon_button = ttk.Button(self.left_frame, style="Overlay.TButton")
        self.icon_button.pack(expand=True, fill="both")

        self.right_frame = ttk.Frame(self.container, style="Overlay.TFrame")
        self.right_frame.place(relx=0.33, rely=0, relwidth=0.67, relheight=1.0)

        for widget in [
            self.container,
            self.left_frame,
            self.right_frame,
            self.icon_button,
        ]:
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<ButtonRelease-1>", self._on_drag_stop)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<Button-3>", self._show_context_menu)

        self.pre_cal_label = ttk.Label(
            self.right_frame, text="", style="Overlay.TLabel", justify="center"
        )
        self.cal_progress_label = ttk.Label(
            self.right_frame, text="0%", style="Overlay.TLabel"
        )
        self.running_frame_label = ttk.Label(
            self.right_frame, text="--", style="Overlay.TLabel"
        )
        self.running_total_label = ttk.Label(
            self.container, text="/--", style="Overlay.Total.TLabel"
        )

        self.timer_container = ttk.Frame(self.container, style="Overlay.TFrame")
        self.timer_icon_label = ttk.Label(self.timer_container, style="Overlay.TLabel")
        self.timer_icon_label.pack(side=tk.LEFT)
        self.timer_label = ttk.Label(
            self.timer_container,
            text="00:00:00",
            style="Overlay.Timer.TLabel",
            cursor="hand2",
        )
        self.timer_label.pack(side=tk.LEFT)
        self.timer_label.bind("<Button-1>", self._on_timer_click)
        for widget in [self.timer_container, self.timer_label, self.timer_icon_label]:
            widget.bind("<Button-3>", self._show_context_menu)

        self.lap_container = ttk.Frame(self.container, style="Overlay.TFrame")
        self.lap_icon_label = ttk.Label(self.lap_container, style="Overlay.TLabel")
        self.lap_icon_label.pack(side=tk.LEFT)
        self.lap_frame_label = ttk.Label(
            self.lap_container, text="0", style="Overlay.Timer.TLabel"
        )
        self.lap_frame_label.pack(side=tk.LEFT)

        logger.debug("Overlay widgets created.")

    def _show_context_menu(self, event: tk.Event) -> None:
        logger.debug("Showing context menu...")
        context_menu = tkMenu(self.root, tearoff=0)

        context_menu.add_cascade(
            label="Calibration", menu=self._create_calibration_submenu(context_menu)
        )
        context_menu.add_cascade(
            label="Display", menu=self._create_display_mode_submenu(context_menu)
        )
        context_menu.add_cascade(
            label="Timer", menu=self._create_timer_adjust_submenu(context_menu)
        )
        context_menu.add_separator()
        context_menu.add_command(label="Exit", command=self._schedule_quit)

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _create_calibration_submenu(self, parent_menu: tkMenu) -> tkMenu:
        submenu = tkMenu(parent_menu, tearoff=0)
        submenu.add_command(
            label="New calibration",
            command=lambda: self.master_callback({"type": "prepare_calibration"}),
        )
        return submenu

    def _create_display_mode_submenu(self, parent_menu: tkMenu) -> tkMenu:
        submenu = tkMenu(parent_menu, tearoff=0)
        modes = {"0_to_n-1": "0 / n-1", "0_to_n": "0 / n", "1_to_n": "1 / n"}
        tk_display_mode = tk.StringVar(value=self.current_display_mode)
        for key, text in modes.items():
            submenu.add_radiobutton(
                label=text,
                variable=tk_display_mode,
                value=key,
                command=lambda m=key: self.master_callback(
                    {"type": "set_display_mode", "mode": m}
                ),
            )
        return submenu

    def _create_timer_adjust_submenu(self, parent_menu: tkMenu) -> tkMenu:
        submenu = tkMenu(parent_menu, tearoff=0)
        is_running = self.active_profile_filename is not None
        cycle_frames = self.current_cycle_total_frames

        def adjust_cb(frames: int) -> None:
            self.master_callback({"type": "adjust_timer", "frames": frames})

        submenu.add_command(
            label=f"Back {cycle_frames}f",
            state="normal" if is_running else "disabled",
            command=lambda: adjust_cb(-cycle_frames),
        )
        submenu.add_command(
            label="Back 1s",
            state="normal" if is_running else "disabled",
            command=lambda: adjust_cb(-FRAMES_PER_SECOND),
        )
        submenu.add_separator()
        submenu.add_command(
            label="Reset",
            state="normal" if is_running else "disabled",
            command=lambda: self.master_callback({"type": "reset_timer"}),
        )
        submenu.add_separator()
        submenu.add_command(
            label="Fwd 1s",
            state="normal" if is_running else "disabled",
            command=lambda: adjust_cb(FRAMES_PER_SECOND),
        )
        submenu.add_command(
            label=f"Fwd {cycle_frames}f",
            state="normal" if is_running else "disabled",
            command=lambda: adjust_cb(cycle_frames),
        )
        return submenu

    def _on_timer_click(self, event: Optional[tk.Event] = None) -> None:
        logger.info("Timer label clicked, sending toggle_lap_timer command.")
        self.master_callback({"type": "toggle_lap_timer"})

    def _hide_all_dynamic_labels(self) -> None:
        self.pre_cal_label.place_forget()
        self.cal_progress_label.place_forget()
        self.running_frame_label.place_forget()
        self.running_total_label.place_forget()
        self.timer_container.place_forget()
        self.lap_container.place_forget()

    def setup_geometry(self, emulator_width: int, emulator_height: int) -> None:
        logger.info(f"Setting overlay geometry for emulator {emulator_width}x{emulator_height}.")
        try:
            self.screen_width = self.root.winfo_screenwidth()
            self.screen_height = self.root.winfo_screenheight()
            logger.info(f"Screen resolution from root: {self.screen_width}x{self.screen_height}")
        except Exception as e:
            logger.warning(f"Could not read screen resolution: {e}")

        try:
            roi_x1, roi_x2, _ = find_cost_bar_roi(self.screen_width, self.screen_height)
            cost_bar_pixel_length = roi_x2 - roi_x1
        except Exception as e:
            logger.warning(f"Could not compute cost bar ROI: {e}, using fallback size.")
            cost_bar_pixel_length = 200

        win_width = int(cost_bar_pixel_length * 5 / 6)
        win_height = int(win_width * 27 / 50)
        logger.info(f"Overlay computed size: {win_width}x{win_height}")

        self.fonts["large_bold"] = tkFont.Font(
            family="Segoe UI", size=-int(win_height * 0.55), weight="bold"
        )
        self.fonts["large_normal"] = tkFont.Font(
            family="Segoe UI", size=-int(win_height * 0.55)
        )
        self.fonts["medium"] = tkFont.Font(
            family="Segoe UI", size=-int(win_height * 0.22)
        )
        self.fonts["small"] = tkFont.Font(
            family="Segoe UI", size=-int(win_height * 0.18)
        )

        self.sizes["offset_x"] = -int(win_width * 0.2)
        self.sizes["padding"] = int(win_height * 0.01)

        self.pre_cal_label.config(font=self.fonts["medium"])
        self.cal_progress_label.config(font=self.fonts["large_normal"])
        self.running_frame_label.config(font=self.fonts["large_bold"])
        self.running_total_label.config(font=self.fonts["medium"])
        self.timer_label.config(font=self.fonts["small"])
        self.lap_frame_label.config(font=self.fonts["small"])

        pos_x = self.screen_width - win_width - 50
        pos_y = self.screen_height - win_height - 100
        self.root.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        logger.info(f"Root geometry set to {win_width}x{win_height}+{pos_x}+{pos_y}")

        button_width = int(win_width * 0.33)
        icon_size = min(button_width, win_height)
        self._resize_icons(icon_size)

        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.wm_attributes("-topmost", True)
        logger.info("Overlay deiconified and lifted.")

    def set_state_running(self, display_total: str, active_profile: str, display_mode: str) -> None:
        logger.info(f"UI state: running (profile='{active_profile}', mode='{display_mode}')")
        self._hide_all_dynamic_labels()
        self.icon_button.config(image=self.icons.get("deco"), command=None)

        self.current_display_mode = display_mode
        self.active_profile_filename = active_profile

        padding = self.sizes.get("padding", 4)
        offset_x = self.sizes.get("offset_x", -40)

        self.running_frame_label.place(relx=1.0, rely=0.4, anchor="e", x=offset_x)
        self.running_total_label.config(text=display_total)
        self.running_total_label.place(relx=1.0, rely=1.0, anchor="se", x=-padding, y=-padding)
        self.timer_container.place(relx=0.0, rely=1.0, anchor="sw", x=padding, y=-padding)

    def update_lap_timer(self, lap_frames: Optional[int]) -> None:
        padding = self.sizes.get("padding", 4)
        if lap_frames is not None:
            self.lap_frame_label.config(text=f"{lap_frames}")
            self.lap_container.place(relx=0.0, rely=0.0, anchor="nw", x=padding, y=padding)
        else:
            self.lap_container.place_forget()

    def _resize_icons(self, size: int) -> None:
        logger.debug(f"Resizing icons to {size}x{size}")
        try:
            timer_height = self.fonts["small"].metrics("linespace")

            for name in ["start", "deco"]:
                path = _resource_path(os.path.join("resource/icons", f"{name}.png"))
                img = Image.open(path).resize((size, size), Image.Resampling.LANCZOS)
                self.icons[name] = ImageTk.PhotoImage(image=img)

            wait_path = _resource_path(os.path.join("resource/icons", "wait.png"))
            wait_img = Image.open(wait_path).resize((size, size), Image.Resampling.LANCZOS)
            self.icons["wait"] = ImageTk.PhotoImage(image=wait_img)

            timer_path = _resource_path(os.path.join("resource/icons", "timer.png"))
            timer_img = Image.open(timer_path).resize(
                (timer_height, timer_height), Image.Resampling.LANCZOS
            )
            self.icons["timer_sized"] = ImageTk.PhotoImage(image=timer_img)
            self.timer_icon_label.config(image=self.icons["timer_sized"])

            lap_path = _resource_path(os.path.join("resource/icons", "wait.png"))
            lap_img = Image.open(lap_path).resize(
                (timer_height, timer_height), Image.Resampling.LANCZOS
            )
            self.icons["lap_sized"] = ImageTk.PhotoImage(image=lap_img)
            self.lap_icon_label.config(image=self.icons["lap_sized"])
        except Exception as e:
            logger.exception(f"Failed to resize icons: {e}")

    def update_running_display(self, display_frame: str, display_total: str) -> None:
        self.running_frame_label.config(text=f"{display_frame}")
        self.running_total_label.config(text=display_total)

    def update_timer(self, time_str: str) -> None:
        self.timer_label.config(text=time_str)

    def _process_ui_queue(self) -> None:
        try:
            message = self.ui_queue.get_nowait()
            msg_type = message.get("type")
            if msg_type != "update":
                logger.debug(f"UI queue message: {message}")

            if msg_type == "update":
                self.update_running_display(
                    message["display_frame"], message["display_total"]
                )
                if "time_str" in message:
                    self.update_timer(message["time_str"])
                if "lap_frames" in message:
                    self.update_lap_timer(message["lap_frames"])
                self.current_cycle_total_frames = message.get("totalFramesInCycle", 0)
            elif msg_type == "geometry":
                self.setup_geometry(message["width"], message["height"])
            elif msg_type == "state_change":
                self._apply_state_change(message)
            elif msg_type == "calibration_progress":
                self.update_calibration_progress(message["progress"])
        except queue.Empty:
            pass
        except Exception:
            logger.exception("Error processing UI queue message")
        finally:
            if self.root and self.root.winfo_exists():
                self.root.after(50, self._process_ui_queue)

    def _apply_state_change(self, message: Dict) -> None:
        self.current_display_mode = message.get("display_mode", "0_to_n-1")
        state = message["state"]
        if state == "running":
            self.set_state_running(
                message["display_total"],
                message["active_profile"],
                self.current_display_mode,
            )
        elif state == "idle":
            self.set_state_idle()
        elif state == "pre_calibration":
            self.set_state_pre_calibration()
        elif state == "calibrating":
            self.set_state_calibrating()

    def _load_icons(self) -> None:
        logger.debug("Loading overlay icons...")
        try:
            for name in ["start", "wait", "deco", "timer"]:
                path = _resource_path(os.path.join("resource/icons", f"{name}.png"))
                img = Image.open(path).convert("RGBA")
                self.icons[name] = ImageTk.PhotoImage(image=img)
            logger.debug("Overlay icons loaded.")
        except FileNotFoundError as e:
            logger.critical(f"Missing icon file: {e.filename}")
            sys.exit(1)

    def _schedule_quit(self) -> None:
        logger.info("Received exit command.")
        self.root.after(0, self._quit_application)

    def _quit_application(self) -> None:
        logger.info("Shutting down overlay...")
        self.root.destroy()
        logger.info("Overlay exited.")

    def set_state_idle(self) -> None:
        logger.info("UI state: idle")
        self._hide_all_dynamic_labels()
        self.icon_button.config(image=self.icons.get("deco"), command=None)
        self.pre_cal_label.config(text="No calibration\nRight-click → Calibrate")
        self.pre_cal_label.place(relx=0.5, rely=0.5, anchor="center")
        self.active_profile_filename = None
        self.current_cycle_total_frames = 0

    def set_state_pre_calibration(self) -> None:
        logger.info("UI state: pre_calibration")
        self._hide_all_dynamic_labels()
        self.icon_button.config(
            image=self.icons.get("start"),
            command=lambda: self.master_callback({"type": "start_calibration"}),
        )
        self.pre_cal_label.config(text="Click icon\nto calibrate")
        self.pre_cal_label.place(relx=0.5, rely=0.5, anchor="center")
        self.active_profile_filename = None
        self.current_cycle_total_frames = 0

    def set_state_calibrating(self) -> None:
        logger.info("UI state: calibrating")
        self._hide_all_dynamic_labels()
        self.icon_button.config(image=self.icons.get("wait"), command=None)
        self.cal_progress_label.place(relx=0.5, rely=0.5, anchor="center")

    def update_calibration_progress(self, percentage: float) -> None:
        self.cal_progress_label.config(text=f"{int(percentage)}%")

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_stop(self, event: tk.Event) -> None:
        self._drag_data["x"] = 0
        self._drag_data["y"] = 0

    def _on_drag_motion(self, event: tk.Event) -> None:
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
