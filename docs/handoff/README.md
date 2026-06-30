# prts-plus Handoff 索引

> 本目录集中存放项目改造过程中的 handoff 文档，方便新 agent 快速了解上下文与当前进度。

## Handoff 文档

| 文件 | 阶段 | 内容概要 |
|------|------|----------|
| `prts-plus-handoff.md` | 项目初始 | 最早的交接文档：可执行状态、依赖环境、打包方式、已解决的 Excel/BitBlt/tesserocr 问题、能力边界与风险提醒。 |
| `cuddly-pondering-fox-handoff.md` | Step 0–6 | 项目改造总览、已完成的 Step 0–6 验证记录、关键文件清单、风险与注意事项。 |
| `handoff_step6.md` | Step 6 | Step 6 完成后的精简交接：帧同步线程 + 悬浮 Overlay UI 的当前状态与验证方式。 |
| `handoff_step7.md` | Step 7 | Step 7 完成交接：离线费用条扫描、`TickStateTracker`、CLI 用法与输出格式。 |
| `handoff_prompt_step8.md` | Step 8 | 给新 agent 的 Step 8 接手 prompt，可直接复制使用。 |
| `handoff_step8.md` | Step 8 | Step 8 完成交接：暂停检测、动作语义识别、JSON 轴生成、CLI 与测试。 |

Handoff 时间线：`prts-plus-handoff.md` → `cuddly-pondering-fox-handoff.md` → `handoff_step6.md` → `handoff_step7.md` → `handoff_step8.md`。

## 项目目标（源自 `cuddly-pondering-fox.md`）

将 `prts-plus` 从 **Excel 宏驱动** 改造为 **JSON 轴 + 命令行/UI 驱动** 的录制/分析/执行系统，并集成 `ArknightsCostBarRuler` 的帧检测与悬浮窗 UI，形成完整闭环：

```
录制 -> 离线分析 -> 生成轴 -> 执行
```

## 当前进度（截至 Step 7）

| Step | 状态 | 说明 |
|------|------|------|
| 0：JSON 轴 / CLI 入口 | ✅ 完成 | `--axis sample-1-7.json --autoenter` 跑通 1-7；`--xlsm` 兼容保留。 |
| 1：MuMu DLL 截图层 | ✅ 完成 | DLL 截图平均 154 FPS；Win32 fallback 已对齐客户区；点击坐标同步修复。 |
| 2：费用条校准 | ✅ 完成 | `calibration/*.json` 生成；`--calibrate` / `scripts/calibrate.py` 可用；验证通过。 |
| 3：视频录制 | ✅ 完成 | `recorder/video_recorder.py` + `scripts/record_actions.py`；帧数/FPS/时间戳均正常。 |
| 4：鼠标监听与坐标转换 | ✅ 完成 | `src/input/` 下鼠标监听、坐标映射、动作聚合；`verify_click_positions.py` 偏差极小。 |
| 5：地图格子识别 | ✅ 完成 | `src/logic/calc_view.py` 实现 `transform_view_to_map`；round-trip 测试通过。 |
| 6：帧检测线程 + 悬浮 Overlay UI | ✅ 完成 | `FrameSource` + `AnalysisWorker` + `OverlayWindow` 已连通；悬浮窗实时显示 tick/计时器。 |
| 7：离线费用条扫描 / 语义识别 | ✅ 完成 | `src/frame/tick_state.py` + `recorder/offline_scanner.py` + `scripts/analyze_recording.py`；录制时保存 timestamps；单元测试通过。 |
| 8：JSON 轴生成 | ⏳ 待开始 | 下一步。 |
| 9：统一入口集成 | ⏳ 未开始 | 把录制/分析/生成轴/执行串联。 |

## 关键文件（最新状态）

| 文件 | 说明 |
|------|------|
| `src/ui/overlay.py` | 悬浮窗本体，单 `ttk.Window` 根窗口。 |
| `src/app.py` | 总装配，连接 capture / analysis / UI。 |
| `src/frame/detector.py` | `AnalysisWorker` + `CostBarDetector`。 |
| `src/frame/frame_source.py` | 帧捕获线程。 |
| `src/frame/calibration.py` | 费用条标定逻辑。 |
| `src/logic/game_time.py` | `GameTime` / `TICK_MAX` 计算。 |
| `src/logic/calc_view.py` | 视图坐标 ↔ 地图 tile 转换。 |
| `src/frame/tick_state.py` | 可复用的 tick/cycle 状态机 `TickStateTracker`。 |
| `recorder/offline_scanner.py` | `OfflineScanner`：读取 MP4 + timestamps，逐帧检测，输出分析 JSON。 |
| `recorder/__init__.py` | 导出 `OfflineScanner`。 |
| `scripts/analyze_recording.py` | 离线扫描 CLI 入口。 |
| `scripts/record_actions.py` | 已修改，录制时保存 timestamps 文件。 |
| `tests/test_offline_scanner.py` | 离线扫描 + 状态机单元测试。 |
| `docs/handoff/handoff_step7.md` | Step 7 详细交接文档。 |

## 验证命令

```bash
# 1. 悬浮窗实时帧检测
.venv\Scripts\python scripts/run_overlay.py

# 2. 录制视频 + 鼠标动作（会同时生成 timestamps）
.venv\Scripts\python scripts/record_actions.py --duration 10

# 3. 离线分析最新录制
.venv\Scripts\python scripts/analyze_recording.py

# 4. 单元测试
.venv\Scripts\python -m unittest tests.test_offline_scanner -v
.venv\Scripts\python -m unittest tests.test_detector_worker -v
```

## 下一步（Step 8）

按 `cuddly-pondering-fox.md` 原计划推进 **Step 8：JSON 轴生成**。基于 Step 7 的 `recording_analysis.json` 和 `actions_*.json`：

- 根据拖拽起点/终点 + `transform_view_to_map` 识别目标 tile
- 根据动作类型（拖拽=部署，短点击=技能/撤退）推断 `action_type`
- 根据操作区域识别干员（待部署区头像匹配）或目标 tile
- 结合 `character_table.json` / `range_table.json` 判断单位是否需要方向
- 输出可直接执行的 JSON axis（类似 `sample 1-7.json`）

## 环境与依赖（来自 `prts-plus-handoff.md`）

- Python 3.11.6，使用项目内 `.venv/` 隔离环境。
- `numpy==1.24.4`、`opencv-python==4.9.0.80`；`tesserocr` 从全局 `site-packages` 拷贝而来。
- 自定义 OCR 模型 `arknights_digit.traineddata` 放在 `tessdata_backup/tessdata/`，打包时由 `run.py` 设置 `TESSDATA_PREFIX`。
- 重新打包命令：

```bash
source .venv/Scripts/activate
pyinstaller -y --name "prts+" --onedir --add-data "resource;resource" --add-data "hook;hook" run.py
cp -r dist/prts+/* .
```

## 已知风险与约束

- **Excel 依赖**：执行 Excel 路径需要安装 Microsoft Excel，WPS 不兼容 `win32com`。
- **MuMu 渲染模式**：默认渲染模式下 `BitBlt` 可能黑屏，需在 MuMu 设置中切换 DirectX / OpenGL 找到兼容模式。
- **Excel 宏 bug**：宏代码里 `--debug` 与 `--autoenter` 之间缺少空格，同时勾选会变成 `--debug--autoenter`；建议优先命令行触发。
- **能力边界**：待部署区单位定位依赖 `resource/operator_mapping.json` + 头像模板匹配；无法自动识别未知单位或判断单位类型/部署规则。
- **窗口方案**：Step 6 已验证单 `ttk.Window` 根窗口在 Windows 下稳定，不要改回父/子窗口方案。
- **初始状态传递**：`OverlayWindow` 的初始状态通过 `set_initial_state(...)` 直接传递，运行时的 tick 更新才走 `ui_queue(maxsize=1)`。

按 `cuddly-pondering-fox.md` 原计划推进：

> **Step 7：离线费用条扫描**
>
> 离线读取录制好的视频，逐帧做 pixel 扫描，生成逻辑帧映射表（`frame_id -> logical_frame -> total_elapsed_frames`）。
>
> 新增 `recorder/offline_scanner.py`：使用 `imageio-ffmpeg` 或 `cv2.VideoCapture` 读取视频，对每一帧调用 `detector.get_logical_frame()`，结合 `frame_timestamps` 输出 `recording_analysis.json`。

## 重要约束

- 不要改回父/子窗口方案；当前单根窗口在 Windows 下稳定。
- 初始状态通过 `overlay.set_initial_state(...)` 直接传递，不要走 `ui_queue`。
- `ui_queue(maxsize=1)` 只用于运行时的 tick 更新。
- 默认截图分辨率 `1280x720`，校准数据在 `calibration/default_30f_1280x720.json`。
