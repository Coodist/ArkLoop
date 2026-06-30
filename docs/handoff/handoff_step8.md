# Handoff: Step 8 — JSON 轴生成

## 当前状态

Step 8 核心链路已实现并单元测试通过：

- `src/frame/pause_detector.py`：暂停帧检测（OCR + 亮度 fallback）。
- `recorder/action_recognizer.py`：动作语义识别（部署 / 技能 / 撤退 / 方向），含头像模板匹配与方向推断。
- `recorder/axis_writer.py`：由 analysis + actions 生成可执行 JSON axis。
- `scripts/generate_axis.py`：CLI 入口，支持自动选取最新录制或显式指定路径。
- `recorder/avatar_patch_recorder.py`：事件化头像 patch 捕获。
- 单元测试：`tests/test_offline_scanner.py`、`tests/test_avatar_patch_recorder.py`、`tests/test_pause_detector.py`、`tests/test_action_recognizer.py`、`tests/test_axis_writer.py`。

## 新增/修改文件

| 文件 | 说明 |
|------|------|
| `src/frame/pause_detector.py` | `is_paused(frame)` / `PauseDetector` 暂停检测。 |
| `recorder/action_recognizer.py` | `ActionRecognizer`、`AvatarMatcher`、`SemanticAction` 等。 |
| `recorder/axis_writer.py` | `AxisWriter` 生成 axis JSON。 |
| `scripts/generate_axis.py` | CLI：生成轴。 |
| `scripts/record_actions.py` | 录制视频+鼠标操作；录制时同步对原始截图检测 tick，写入 timestamps JSON；支持 `--no-video`。 |
| `recorder/offline_scanner.py` | 注入可选 `pause_detector` 参数；新增 `detect_tick_anomalies` 与最终警告；优先使用 timestamps 里预存的 tick。 |
| `recorder/video_recorder.py` | H.264 视频录制（现在主要作备份/可视化，tick 优先从录制时预存数据读取）。 |
| `recorder/avatar_patch_recorder.py` | 事件化头像 patch 捕获：拖拽开始时监听鼠标离开待部署区，保存无遮挡 patch。 |
| `scripts/analyze_recording.py` | 新增 `--detect-pause` 开关；分析结束打印 tick 异常摘要。 |
| `sync_new_resource.py` | 支持 `--skip-git`、单仓库失败继续、resource 目录回退。 |
| `scripts/generate_unit_metadata.py` | 独立生成 `unit_metadata.json`，网络不畅时使用。 |
| `tests/test_offline_scanner.py` | 离线扫描、cycle wrap、tick 异常、预存 tick 回退测试。 |
| `tests/test_avatar_patch_recorder.py` | 头像 patch 捕获单元测试。 |
| `tests/test_pause_detector.py` | 暂停检测测试。 |
| `tests/test_action_recognizer.py` | 部署/技能/撤退/方向识别测试。 |
| `tests/test_axis_writer.py` | 轴生成与 `load_axis_from_json` 兼容性测试。 |
| `docs/handoff/handoff_step8.md` | 本文档。 |

## 使用方式

### 1. 录制（同步检测 tick）

```bash
.venv\Scripts\python scripts/record_actions.py --duration 10
```

录制时会同步检测每一帧的 tick，并把 `(frame_id, timestamp, tick)` 写入 `recordings/recording_<ts>_timestamps.json`。

### 2. 离线分析

```bash
.venv\Scripts\python scripts/analyze_recording.py
```

如果 timestamps JSON 里有 `frame_ticks`，分析会直接使用这些预存 tick，不再从压缩后的 MP4 重新识别。

### 3. 生成 JSON 轴

自动模式（取 recordings/ 下最新 analysis + actions）：

```bash
.venv\Scripts\python scripts/generate_axis.py --map-code 1-7
```

显式指定路径：

```bash
.venv\Scripts\python scripts/generate_axis.py `
  --analysis recordings/recording_20260619_165714_analysis.json `
  --actions recordings/actions_20260619_165714.json `
  --map-code 1-7 `
  --output axis_20260619_165714.json
```

### 4. 验证生成的轴

```bash
.venv\Scripts\python -c "from src.axis.json_loader import load_axis_from_json; load_axis_from_json('axis_<ts>.json')"
```

### 5. 单元测试

```bash
.venv\Scripts\python -m unittest tests.test_offline_scanner tests.test_avatar_patch_recorder tests.test_pause_detector tests.test_action_recognizer tests.test_axis_writer -v
```

## 录制时同步检测 tick

从 `scripts/record_actions.py` 的录制链路来看，视频会先经过 H.264 压缩，离线再从 MP4 重新检测 tick 时容易因压缩边缘模糊导致抖动。因此改为：

1. 每次截图后立即用 `CostBarDetector.detect_tick()` 在原始无损帧上测 tick。
2. 把结果写入 `recording_<ts>_timestamps.json` 的 `frame_ticks` 字段。
3. `recorder/offline_scanner.py` 优先读取 `frame_ticks`；没有该字段的旧录像才回退到视频重分析。

这样做的好处：

- 与实时 overlay 同源同逻辑，一致性最高。
- 不受 CRF/yuv420p 压缩影响。
- 检测开销很小（1~3 ms/帧），不会拖慢录制。

## 事件化头像匹配

部署干员时，鼠标会遮挡头像，且被选中的头像会向上弹起。为了获得更干净的头像：

1. `record_actions.py` 每帧截图的同时，把帧推入 `AvatarPatchRecorder` 的 ring buffer。
2. `MouseListener` 的回调只更新 `AvatarPatchRecorder` 的鼠标位置和拖拽状态，**不额外截图**。
3. 当检测到拖拽且鼠标离开待部署区时，从 ring buffer 取出最近帧，裁剪该槽位的大范围 patch（覆盖弹起前后位置），保存为 `recordings/patches_<ts>/avatar_patch_<start_ts>.png`。
4. `ActionRecognizer` 优先使用预存 patch 做模板匹配；没有 patch 才回退到视频帧。

这样可以：

- 避免鼠标遮挡头像。
- patch 范围足够大，吸收头像被选中的向上偏移。
- 不依赖 MP4 视频，头像匹配可以和视频录制解耦。
- 不会双倍截图（事件回调不做截图，只共享主循环的截图流）。

### 关闭视频录制

如果你确认不需要视频备份，可以只保存 timestamps/actions/patches：

```bash
.venv\Scripts\python scripts/record_actions.py --no-video --duration 10
```

## Tick 异常检测可见性

离线扫描完成后，`detect_tick_anomalies` 会逐帧比较相邻 tick，并在日志与终端输出警告：

- **forward_jump**：同一 cycle 内 tick 一次性前进 2 步以上（如 `5 -> 7`、`2 -> 25`）。
- **backward_noise**：非边界 wrap 的后退跳变（如 `26 -> 25`、`25 -> 24`）。

有效 cycle wrap 仍按 `ArknightsCostBarRuler` 的边界规则判定：
`previous > TICK_MAX * 0.75` 且 `current < TICK_MAX * 0.25`。

异常帧会列出 `frame_id`、`timestamp`、前后 tick 与类型，便于定位 OCR/校准不稳定的帧。

## 同步脚本网络问题处理

如果拉取仓库时遇到 `Recv failure: Connection was reset`：

```powershell
# 方案 A：设置代理
$env:HTTPS_PROXY="http://127.0.0.1:7890"
.venv\Scripts\python sync_new_resource.py

# 方案 B：跳过 git，只使用本地 resource/ 目录生成 mapping
.venv\Scripts\python sync_new_resource.py --skip-git

# 方案 C：手动生成 unit_metadata
.venv\Scripts\python scripts/generate_unit_metadata.py `
  --character-table ...\character_table.json `
  --range-table ...\range_table.json `
  --operator-mapping resource\operator_mapping.json `
  --output new_resource\unit_metadata.json
```

## 已知限制

- **头像匹配**：依赖清晰的待部署区截图与 `resource/avatar/` 模板；夜间/模糊帧会识别为 `unknown`。
- **方向推断**：优先使用紧随其后的方向小拖拽，或拖拽终点相对目标格中心的偏移推断；无法识别时默认 `"右"`。
- **视角选择**：每次地图点击比较正视图/侧视图投影距离，取更近且可部署的；仍不明确默认正视图。
- **费用 OCR**：失败时 `cost` 降级为 `0`。
- **暂停 OCR**：当前 tessdata 路径下可能没有 `eng` 语言包，会回退到亮度 heuristic；如需 OCR 生效，请确保 `TESSDATA_PREFIX` 包含 `eng.traineddata`。
- **Tick 异常警告**：边界规则会过滤正常 wrap，但如果单帧 OCR 抖动频繁触发警告，说明费用条校准或识别不稳定，建议检查校准质量或提高录制分辨率。

## 下一步（Step 9）

按原计划推进 **Step 9：统一 GUI/CLI**，将 `record_actions.py`、`analyze_recording.py`、`generate_axis.py`、`run.py --axis` 等入口整合到一个统一的 UI 工作流中。
