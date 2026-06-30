# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PRTS+ (product name **ArkLoop**) is an Arknights frame-operation assistance tool for
**Windows + MuMu 12 emulator**. It **records** gameplay into an "axis" (时间轴 / timeline of
operator actions), reconstructs per-frame game state via computer vision + OCR on the
captured frames, and **replays** that axis with frame-level precision (bullet-time + frame
stepping). There is also a React timeline editor for hand-editing axes.

> ⚠️ **Read this section before trusting any other doc.** This codebase is easy to misread.
> The points below are the mistakes AI assistants make most often:
>
> 1. **The app is a PyWebview desktop app, not a CLI.** The real entry point is
>    `scripts/arkloop_webview.py` (class `ArkLoopApi`), which loads the React UI from
>    `ui/dist/` and exposes recording + playback over `pywebview.api`. `run.py` / `src/main.py`
>    is a **legacy execute-only CLI** (`--axis`, `--xlsm`, `--calibrate`) — it cannot record.
> 2. **Recording is LIVE, not an offline FFmpeg pipeline.** The live recorder
>    (`recorder/backend.py::ActionBackend`) captures frames in real time and builds the axis
>    on the fly. `recorder/video_recorder.py` (FFmpeg/`VideoRecorder`) and the offline scanner
>    are an **older path that the running app does not use**. Don't describe the system as a
>    "record video → analyze offline → generate axis" pipeline; that's stale.
> 3. **Everything MuMu-specific funnels through one function:**
>    `src/mumu/mumu_connection.py::get_handle()`. It resolves a **two-level** window
>    (parent `FindWindow` by title + render **sub-window** `EnumChildWindows` by exact title).
>    Capture, input injection, recording's foreground filter, and coordinate mapping all depend
>    on it. This is the seam for any multi-platform work.
> 4. **Data lives in `resource/`, not `new_resource/`.** There is no `new_resource/` directory.

## Development Commands

### Primary app (PyWebview + React)

```bash
# Build the frontend first (required — the app loads ui/dist/index.html)
cd ui && npm install && npm run build      # → ui/dist/
cd ui && npm run dev                        # Vite dev server (frontend iteration only)

# Run the desktop app
.venv\Scripts\python scripts/arkloop_webview.py
.venv\Scripts\python scripts/arkloop_webview.py --dev-tools     # right-click → Inspect
.venv\Scripts\python scripts/arkloop_webview.py --debug-mouse   # log raw mouse + mapped ratio

# Build executable (output: dist/ArkLoop/ArkLoop.exe)
pyinstaller arkloop.spec
```

### Legacy execute-only CLI (`run.py` → `src/main.py`)

```bash
.venv\Scripts\python run.py --axis <path.json>   # Replay a JSON axis (uses AxisRunner)
.venv\Scripts\python run.py --xlsm <path.xlsm>   # Replay a legacy Excel axis
.venv\Scripts\python run.py --calibrate          # Cost-bar calibration → calibration/*.json
.venv\Scripts\python run.py --axis <p> --debug   # Verbose logging
```

### Tests

```bash
.venv\Scripts\python -m unittest discover -v tests
.venv\Scripts\python -m unittest tests.test_action_archive -v
```

## Architecture

Two user-facing flows, both driven by `ArkLoopApi` in `scripts/arkloop_webview.py`. They share
the capture + frame-analysis + projection layers, and both reach the emulator only through
`src/mumu/`.

### Flow A — Recording (live axis generation)

`ArkLoopApi.start_recording` → `recorder/backend.py::ActionBackend`, which wires together:

- **`src/frame/frame_source.py::FrameSource`** — background thread that calls
  `capture_game_window` at ~30 fps and publishes the latest frame to a `maxsize=1` queue.
- **`src/frame/detector.py::AnalysisWorker` + `CostBarDetector`** — reads the cost bar pixel
  width each frame to recover in-game time as `(cycle, tick)`. Calibration comes from the
  user-selected `calibration/*.json`.
- **`src/input/mouse_listener.py::MouseListener`** — pynput global mouse hook. Records
  **screen-absolute** events, but **only while MuMu is the foreground window**
  (`_is_mumu_foreground()` compares `GetForegroundWindow()` to `get_handle()`/parent).
- **`src/input/coordinate_mapper.py::CoordinateMapper`** — maps screen-absolute → MuMu
  client-area ratio (0–1), then to the standard 1280×720 canvas.
- **`recorder/action_recognizer.py` + `recorder/action_worker.py`** — classify each mouse
  action as Deploy / Skill / Retreat / Direction using avatar template matching
  (`resource/avatar/`) and MAA recognition (`src/maa/`), correlated with the tick state.
- **`recorder/backend.py::AxisBuilder`** — aggregates semantic actions into axis dicts
  (holds deploys until their direction-drag arrives) → JSON written by `write_axis_json`.

Output axis JSON: `{settings: {map_code, max_tick, ...}, actions: [{cycle, tick, action_type,
oper, pos, direction, ...}]}` — saved under `timelines/`.

### Flow B — Playback (axis execution)

`ArkLoopApi.start_playback` (and `run.py --axis`) → `src/axis/axis_runner.py::AxisRunner` →
`src/logic/perform_action.py`:

- Loads the axis via `src/axis/json_loader.py`, projects board positions to screen via
  `src/logic/calc_view.py` (front/side view transforms), tracks game time via
  `src/logic/time_source.py::PlaybackTimeSource` (same cost-bar detection as recording).
- For each action: resume the game, wait until near the target frame, **pause**, **step frame
  by frame** to the exact tick, then perform the deploy/skill/retreat while paused
  ("pause invariant"). Bullet-time + frame-step is the core timing trick.
- All input goes through `src/mumu/mumu_controller.py` (see below).

### The MuMu boundary (`src/mumu/`)

| File | Role |
|---|---|
| `mumu_connection.py` | **`get_handle()` — the single choke point.** Resolves MuMu parent window (`FindWindow` by `window_name`) + render sub-window (`EnumChildWindows`, **exact** `sub_window_name` match). Caches + re-finds when the handle goes stale (MuMu recreates the sub-window across scenes). |
| `mumu_vision.py` | `capture_game_window(ratio, color)` — screenshot normalized to 1280×720. `create_capture_controller()` picks **MuMu DLL** (`MuMuPlayerController`, needs `mumu.install_path`) or **Win32 BitBlt** fallback per `config.json` `capture_type`. |
| `mumu_dll_controller.py` / `win32_capture.py` | The two capture backends behind `capture_controller.py::BaseCaptureController`. |
| `mumu_controller.py` | **Input injection.** `mouseclick/down/up/move` send `WM_LBUTTON*` via `SendMessage` to the handle (background input — no focus needed). `pause()`/`esc()` send `WM_XBUTTON1/2`, which **depend on the MuMu key-mapping scheme** (`PRTS+键鼠方案示例.json`) binding the mouse side-buttons to the game's pause/cancel. Frame-stepping in `perform_action.py` is built on the `pause()`+`esc()` timing pair. |

### Shared / platform-neutral layers (operate on a normalized 1280×720 frame or pure data)

| Path | Role |
|---|---|
| `src/frame/` | Cost-bar tick detection (`detector.py`), pause detection (`pause_detector.py`), calibration (`calibration.py`), `tick_state.py`, `frame_source.py`. |
| `src/logic/` | `perform_action.py` (execution state machine), `calc_view.py` / `convert_pos.py` (board↔screen projection), `game_time.py` / `time_source.py` / `analyze_time.py` (game-time math), `locate_avatar.py`, `auto_enter.py`. |
| `src/maa/` | MAA framework recognition (slot layout, side-view OCR, ROIs). `maa` is bundled in `.venv`. |
| `src/axis/` | `axis_runner.py` (playback engine, shared by webview + CLI), `json_loader.py`. |
| `recorder/` | Live recording backend + semantic recognition (Flow A). |
| `ui/` | React + Vite + Tailwind timeline editor; builds to `ui/dist/`. |

### Config & data

- **`config.json`** (next to the EXE when frozen) — `capture_type` (`auto`/`mumu`/`win32`) and
  `mumu.{install_path, instance_index, window_name, sub_window_name}`. Read live on each handle
  re-find, but the capture controller is cached on first use, so capture-source changes need a
  restart.
- **`resource/`** — game data: `avatar/` (operator avatar templates), `level_code_mapping.json`,
  `level_name_mapping.json`, maps. `character_table.json` (root) is the operator metadata source.
  (There is **no** `new_resource/`.)
- **`calibration/*.json`** — cost-bar calibration per resolution/fps (e.g.
  `default_30f_1280x720.json`). Axis ticks are calibration-relative; the recording and the
  replay must use a matching profile or the playhead drifts.
- **`timelines/`** — user axis JSONs + `.meta.json` (pinned state + presets). Lives next to the
  EXE when frozen so it survives reinstalls.

## Important constraints

- **Windows only** — Win32 API (pywin32), MuMu emulator SDK, MAA framework.
- **Python 3.11 recommended** — `tesserocr` wheel requires the exact version.
- **MuMu 12 only** — capture + input assume MuMu's window structure and key-mapping. Set MuMu to
  **1280×720, DirectX**. Don't open via a multi-instance launcher (window titles change).
- Axis files are **calibration-relative** — replay calibration must match the recording's.
- The React UI is required for the main app (the webview loads `ui/dist/index.html`); the legacy
  CLI runs headless.

## UI timeline — critical invariants (easy to silently break)

### Fixed left column is 220 px — scroll container starts after it
`Timeline.tsx` splits into a fixed `w-timeline-left` (220 px) left column (TransportControls
+ row labels) and a right `overflow-x: auto` scroll container.  `DEFAULT_LAYOUT.leftMargin = 0`
because ticks are numbered from x = 0 inside the scroll container.  `Ruler` also receives
`leftMargin = 0`.  The `w-timeline-left` Tailwind token in `tailwind.config.ts` controls the
fixed column width; the scrollbar naturally only spans the right content area.
If you change the 220 px value, update both `tailwind.config.ts` and the `w-timeline-left`
class on the fixed column in `Timeline.tsx`.

### Pentagon coordinate system
`block.x` = the tick's x position in scroll-container space.
- Tip (leftmost point) is AT `block.x` — aligns with the tick's dashed grid line.
- Rectangular body starts at `block.x + pointLength`, ends at `block.x + pointLength + block.width`.
- `foreignObject` (avatars/pos) starts at `block.x + pointLength + 4`.
- `block.endX` in layout = `block.x + pointLength + block.width` — this is the **visual** end
  used for collision avoidance in `useTimelineLayout`. If you change the shape, update `endX` too.

### Row labels must use `flex-1`, never explicit `height`
The three row-label divs (部署/技能/撤退) in `Timeline.tsx` use `flex-1` to fill exactly the
space between `top-[43px]` and `bottom-0`. Using `style={{ height: rowHeight }}` causes
floating-point accumulation errors that clip the retreat row at small window sizes.

### Ruler tick x-values are in scroll-container space, not ruler-SVG space
The Ruler SVG sits inside a `flex-1` div that starts at x = `leftMargin` (220px) in the scroll
container. All `t.x` values from `useTimelineLayout` are absolute scroll-container coordinates.
Inside Ruler, render at `t.x - leftMargin` to get the correct SVG-local position. Forgetting this
shifts every tick label 220px to the right of its grid line.

### `containerHeight` must not have a large Math.max floor
`setContainerHeight(Math.max(1, el.clientHeight - TOP_BAR_HEIGHT))`. A floor ≥ row height
(e.g. the old `Math.max(120, ...)`) inflates the SVG height beyond the scroll container and clips
the retreat row under `overflow-y-hidden`.

### `timelines/.meta.json` is the pinned-state store — never glob it
`list_timelines()` filters with `not p.name.startswith('.')`. Do not change this filter or the
pinned metadata file will appear as a loadable timeline.

### Toolbar row is intentionally empty
`App.tsx` has a `h-8 bg-panel border-y border-border-panel shrink-0` div with no children.
This is a placeholder — do not remove it or add recording controls there.
