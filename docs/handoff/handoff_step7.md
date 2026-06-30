# Handoff: Step 7 完成 — 离线费用条扫描

## 当前状态

Step 7 已完成并验证通过：

- 录制视频时同步保存 `recording_<ts>_timestamps.json`，包含每帧时间戳。
- 新增 `recorder/offline_scanner.py`，可离线读取录制视频，逐帧调用费用条检测器。
- 新增 `src/frame/tick_state.py` 中的 `TickStateTracker`，复用 `cycle_counter` / `total_elapsed_frames` 状态机。
- 新增 `scripts/analyze_recording.py` CLI 入口，支持：
  - 分析最新录制对
  - 指定视频 + timestamps
  - 可选关联 `actions_*.json` 做语义时间标注
- 输出 `recording_analysis.json`：含每帧的 `frame_id` / `timestamp` / `tick` / `cycle` / `total_elapsed_frames` / `paused`。

## 关键文件

| 文件 | 说明 |
|------|------|
| `src/frame/tick_state.py` | 可复用的 tick/cycle 状态机 `TickStateTracker`。 |
| `recorder/offline_scanner.py` | `OfflineScanner`：读取 MP4 + timestamps，逐帧检测，输出分析 JSON。 |
| `recorder/__init__.py` | 导出 `OfflineScanner`。 |
| `scripts/analyze_recording.py` | 离线扫描 CLI 入口。 |
| `scripts/record_actions.py` | 已修改，录制时保存 timestamps 文件。 |
| `tests/test_offline_scanner.py` | 离线扫描 + 状态机单元测试。 |
| `scripts/verify_step7.py` | 一键验证脚本：单元测试 + 最新录制离线扫描 + 输出校验。 |

## 使用方式

### 1. 录制时自动生成 timestamps

```bash
.venv\Scripts\python scripts/record_actions.py --duration 10
```

现在会同时生成三个文件：

- `recordings/recording_<ts>.mp4`
- `recordings/recording_<ts>_timestamps.json`
- `recordings/actions_<ts>.json`

### 2. 离线分析最新录制

```bash
.venv\Scripts\python scripts/analyze_recording.py
```

默认读取 `recordings/` 下最新的一对视频+timestamps，输出 `recordings/recording_<ts>_analysis.json`。

### 3. 指定输入并关联 actions

```bash
.venv\Scripts\python scripts/analyze_recording.py \
  --video recordings/recording_20260619_123456.mp4 \
  --timestamps recordings/recording_20260619_123456_timestamps.json \
  --actions recordings/actions_20260619_123456.json \
  --output analysis/my_analysis.json
```

### 4. 只扫描前 N 帧做快速测试

```bash
.venv\Scripts\python scripts/analyze_recording.py --max-frames 60
```

## 输出格式示例

```json
{
  "metadata": {
    "video_path": "recordings/recording_20260619_165714.mp4",
    "timestamps_path": "recordings/recording_20260619_165714_timestamps.json",
    "fps": 30.0,
    "frame_count": 299,
    "duration": 9.967,
    "ticks_per_cycle": 30,
    "detector_ready": true,
    "calibration_profile": { ... },
    "scanned_frames": 299
  },
  "frames": [
    {
      "frame_id": 0,
      "timestamp": 0.0,
      "tick": 0,
      "cycle": 0,
      "total_elapsed_frames": 0,
      "paused": false
    },
    ...
  ]
}
```

如果传了 `--actions`，输出会多一个 `actions` 字段，每个 action 附带 `game_time`：

```json
{
  "type": "drag",
  "start_ts": 2.65,
  "game_time": {
    "frame_id": 79,
    "tick": 19,
    "cycle": 0,
    "total_elapsed_frames": 19,
    "timestamp": 2.633
  }
}
```

## 验证命令

```bash
# 单元测试
.venv\Scripts\python -m unittest tests.test_offline_scanner -v

# 实际离线分析（需已有录制）
.venv\Scripts\python scripts/analyze_recording.py
```

## 已修复/注意的问题

1. **frame_timestamps 未持久化** → `record_actions.py` 现在把 timestamps 写入 `recording_<ts>_timestamps.json`。
2. **状态机逻辑复用** → `TickStateTracker` 与 `AnalysisWorker` 行为一致：tick 为 `None` 时 `paused=True`，但 `current_tick` 保留最后已知值。
3. **时间戳不匹配** → 若 timestamps 数量与解码帧数不一致，离线扫描会打印警告并对缺失项回退到 `frame_index / fps`。

## 已知限制

- `--actions` 关联目前只把每个 action 映射到最近帧的游戏时间，尚未推断 `部署/技能/撤退` 类型、干员、方向等语义。这些属于 Step 8（JSON 轴生成）。
- 离线扫描依赖已存在的费用条校准文件（`calibration/default_30f_1280x720.json`），否则退化为默认 `ticks_per_cycle=30` 且无法检测 tick。
- 视频解码使用 OpenCV；若录制编码特殊，可能需要额外安装解码器。

## 下一步（Step 8）

按 `cuddly-pondering-fox.md` 原计划推进 **Step 8：JSON 轴生成**。基于 Step 7 的 `recording_analysis.json` 和 `actions_*.json`：

- 根据拖拽起点/终点 + `transform_view_to_map` 识别目标 tile
- 根据动作类型（拖拽=部署，短点击=技能/撤退）推断 `action_type`
- 根据操作区域识别干员（待部署区头像匹配）或目标 tile
- 结合 `character_table.json` / `range_table.json` 判断单位是否需要方向
- 输出可直接执行的 JSON axis（类似 `sample 1-7.json`）
