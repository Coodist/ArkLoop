# prts-plus 录制-识别-生成轴流程文档

本文档描述 `prts-plus` 中从**录制玩家操作**到**生成可执行 JSON 轴**的完整流水线，以及生成的轴如何被消费执行。

---

## 一、整体架构

整个流程分为五个阶段：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   1. 录制阶段    │───▶│  2. 离线分析阶段  │───▶│  3. 语义识别阶段  │
│                 │    │                 │    │                 │
│  video + mouse  │    │  tick/pause     │    │  deploy/skill/  │
│  + tick + patch │    │  reconstruction │    │  retreat 识别   │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                                                       ▼
┌─────────────────┐    ┌─────────────────┐
│   5. 执行阶段    │◀───│  4. 轴生成阶段   │
│                 │    │                 │
│  axis_runner    │    │  JSON axis      │
│  perform_action │    │  (cost+tick)    │
└─────────────────┘    └─────────────────┘
```

---

## 二、阶段 1：录制阶段

入口脚本：`scripts/record_actions.py`

### 2.1 同步时间原点

录制开始时，所有子系统共享同一个时间原点 `shared_start_ts = time.perf_counter()`：

- 视频帧时间戳
- 鼠标事件时间戳
- 预计算的 tick 时间戳

这是后续把鼠标动作对齐到费用条帧数的基础。

### 2.2 视频录制

**文件**：`recorder/video_recorder.py`

- 使用 `imageio-ffmpeg` 调用 FFmpeg
- 输入：原始 BGR 帧序列（通过 `capture_game_window` 捕获）
- 输出：`recordings/recording_<ts>.mp4`
- 同时记录每帧时间戳，存入 `recording_<ts>_timestamps.json`

关键设计：
- `maxsize=1` 队列思想不存在，这里是直接按固定 FPS 循环捕获
- 视频压缩后再次分析会有画质损失，所以同时做了**预计算 tick**

### 2.3 鼠标事件录制

**文件**：
- `src/input/mouse_listener.py`：全局低层鼠标钩子
- `src/input/action_recorder.py`：原始事件聚合成 click/drag/scroll
- `src/input/coordinate_mapper.py`：屏幕坐标 → 游戏比例坐标

#### MouseListener

- 基于 `pynput` 安装全局鼠标钩子
- 只记录 **MuMu 模拟器窗口在前台时**的事件
- 可选记录鼠标移动（`record_moves=True`），用于重建拖拽路径
- 时间戳使用 `time.perf_counter()`，与视频共享原点

#### ActionRecorder

把原始 `mousedown`/`mouseup` 聚合成高级动作：

| 原始事件 | 聚合结果 | 判断条件 |
|---------|---------|---------|
| mousedown + mouseup，距离小 | `click` | 移动距离 < `DRAG_THRESHOLD_RATIO` |
| mousedown + mouseup，距离大 | `drag` | 移动距离 ≥ `DRAG_THRESHOLD_RATIO` |
| scroll | `scroll` | 直接记录 |

输出格式示例（`recordings/actions_<ts>.json`）：

```json
{
  "start_ts": 1234567890.123,
  "duration": 45.2,
  "action_count": 12,
  "actions": [
    {
      "type": "drag",
      "start_ts": 1.23,
      "end_ts": 1.56,
      "start_ratio": {"x": 0.12, "y": 0.85},
      "end_ratio": {"x": 0.45, "y": 0.42},
      "button": "left",
      "raw_events": [...]
    }
  ]
}
```

### 2.4 头像 Patch 录制

**文件**：`recorder/avatar_patch_recorder.py`

用途：在部署拖拽发生时，自动截取被拖拽干员的头像 patch，供后续识别干员名使用。

工作流程：
1. 监听鼠标事件，检测从左键在待部署区按下的拖拽
2. 维护最近 N 帧的帧环缓冲（`deque(maxlen=...)`）
3. 当鼠标离开待部署区（`ratio_y < OPERATOR_AREA_TOP - 0.03`）时，从环缓冲中找到拖拽开始时刻附近的帧
4. 裁剪该帧中拖拽起点周围的头像区域
5. 保存为 `recordings/patches_<ts>/avatar_patch_<start_ts>.png`
6. 把 patch 路径回填到对应 drag 动作的 `avatar_patch` 字段

关键设计：
- 不额外截图，复用视频录制同一次捕获的帧
- 在鼠标离开待部署区时保存，避免鼠标光标遮挡头像

### 2.5 Tick 预计算

在录制循环中，每捕获一帧就立即对该帧运行费用条检测：

```python
pil_img = Image.fromarray(frame).convert("RGB")
tick = detector.detect_tick(pil_img)
frame_ticks.append({
    "frame_id": frame_idx,
    "timestamp": now - shared_start_ts,
    "tick": tick,
})
```

原因：H.264 压缩后的视频再解码分析会引入抖动，所以**在录制时就把 tick 算好**，离线分析时优先使用预计算值。

输出：`recording_<ts>_timestamps.json` 中的 `frame_ticks` 字段。

---

## 三、阶段 2：离线分析阶段

入口脚本：`scripts/analyze_recording.py`

**文件**：`recorder/offline_scanner.py`

### 3.1 输入数据

- `recording_<ts>.mp4`：视频（备用）
- `recording_<ts>_timestamps.json`：时间戳 + 预计算 tick
- `actions_<ts>.json`：鼠标动作（可选，用于语义标注）

### 3.2 帧扫描流程

`OfflineScanner.scan()` 优先使用预计算 tick：

```python
if frame_ticks exist in timestamps:
    _scan_from_precomputed_ticks(...)
else:
    _scan_from_video(...)  # 解码视频重新跑检测
```

#### 使用预计算 tick

直接读取 `frame_ticks`，用 `TickStateTracker` 维护 cycle/total_elapsed_frames：

```python
state = tracker.update(tick)
frames.append({
    "frame_id": frame_idx,
    "timestamp": ts,
    "tick": state["tick"],
    "cycle": state["cycle"],
    "total_elapsed_frames": state["total_elapsed_frames"],
    "paused": state["paused"],
})
```

#### 从视频解码（fallback）

使用 `cv2.VideoCapture` 逐帧读取，对每帧运行 `CostBarDetector.detect_tick()`。

### 3.3 Tick 状态机

**文件**：`src/frame/tick_state.py`

`TickStateTracker` 负责：
- 维护 `current_tick`、`last_tick`
- 检测 cycle wrap（从 tick 高位跳到低位）
- 计算 `total_elapsed_frames = cycle_counter * ticks_per_cycle + tick`
- 判断 paused（tick 为 None 时表示暂停）

Wrap 判定条件（与 ArknightsCostBarRuler 一致）：

```python
if last_tick > ticks_per_cycle * 0.75 and tick < ticks_per_cycle * 0.25:
    cycle_counter += 1
```

### 3.4 暂停检测

**文件**：`src/frame/pause_detector.py`

有两套暂停判定：

1. **基于 tick**：tick 检测返回 None → paused
2. **基于画面**：检测画面中心是否变暗（暂停遮罩），用于处理子弹时间等 tick 卡住的情况
3. **启发式**：连续多帧 tick 不变 → 标记为 paused

```python
mark_stuck_ticks_as_paused(frames, consecutive_threshold=12)
```

### 3.5 Tick 异常检测

`detect_tick_anomalies()` 扫描相邻帧的 tick 变化，标记两类异常：

- `forward_jump`：一帧内 tick 前进超过 1（可能是检测跳变）
- `backward_noise`：非 cycle wrap 情况下的 tick 下降（可能是误检）

### 3.6 动作时间对齐

`OfflineScanner.annotate_actions()` 把鼠标动作的时间戳对齐到帧序列：

- 找到动作 `start_ts` 时刻最接近的帧
- 把该帧的 `tick`、`cycle`、`total_elapsed_frames` 回填到动作上
- 这样每个动作都知道它发生在费用条的哪一帧

输出：`analysis/recording_<ts>_analysis.json`

---

## 四、阶段 3：语义识别阶段

**文件**：`recorder/action_recognizer.py`

### 4.1 输入

- 离线扫描结果 `analysis.json`
- 鼠标动作 `actions.json`
- 地图数据 `cache.py` 加载的 `level_data`

### 4.2 识别流程

`ActionRecognizer.recognize(raw_actions, frames)` 逐个处理动作：

#### Step 1：获取动作发生时的游戏时间

```python
game_time = find_nearest_frame(action.start_ts)
```

#### Step 2：判断动作类型

| 动作特征 | 识别结果 | 说明 |
|---------|---------|------|
| 拖拽起点在待部署区，终点在战场 | `DEPLOY`（部署） | 最常见 |
| 点击在撤退按钮区域 | `RETREAT`（撤退） | 固定 ROI 判定 |
| 点击在技能按钮区域 | `SKILL`（技能） | 固定 ROI 判定 |
| 其他（拖动视角、点暂停等） | `IGNORE`（忽略） | 过滤掉 |

撤退/技能按钮区域是硬编码的四边形：

```python
RETREAT_QUAD = [(0.432, 0.251), (0.503, 0.235), (0.430, 0.351), (0.504, 0.338)]
SKILL_QUAD   = [(0.635, 0.515), (0.725, 0.504), (0.644, 0.672), (0.746, 0.662)]
```

#### Step 3：部署动作进一步解析

对于 `DEPLOY`：
1. 用 `AvatarMatcher` 匹配拖拽起点处的头像 patch，识别干员名
2. 用 `calc_view.transform_view_to_map()` 把拖拽终点屏幕坐标反投影到地图 tile
3. 判断方向拖拽：如果释放后还有一个短拖拽，且终点在目标 tile 周围的菱形区域内，则判定为方向

方向菱形判定：

```python
DIRECTION_DRAG_TILE_RADIUS = 2.5
corner_tiles = [
    (row, col - radius),  # 左 → 朝右
    (row + radius, col),  # 下 → 朝上
    (row, col + radius),  # 右 → 朝左
    (row - radius, col),  # 上 → 朝下
]
```

通过看方向拖拽终点落在哪个象限，推断朝向。

#### Step 4：维护场上状态

`ActionRecognizer` 内部维护：
- `deployed_operators`：已部署干员 → tile 位置
- 这样后续点击地图的 `skill`/`retreat` 可以根据点击位置反推是哪个干员

### 4.3 AvatarMatcher

**文件**：`recorder/action_recognizer.py` 中的 `AvatarMatcher`

- 加载所有已知干员头像模板（`src/cache.get_avatars()`）
- 对录制时保存的 `avatar_patch` 做模板匹配
- 返回最佳匹配的干员名

如果匹配失败，会使用 patch 文件路径或标记为未知。

---

## 五、阶段 4：轴生成阶段

**文件**：`recorder/axis_writer.py`

### 5.1 输入

- `analysis_data`：离线扫描结果
- `actions_data`：带 patch 的鼠标动作
- `map_code`：关卡代码，如 `"1-7"`

### 5.2 生成流程

1. 实例化 `ActionRecognizer`，传入地图数据和帧提供器
2. 调用 `recognizer.recognize()` 得到语义动作列表 `semantic_actions`
3. 对每个语义动作：
   - 过滤掉 `IGNORE`
   - 从对应时刻的视频帧中 OCR 费用数字，得到 `cost`
   - 把 tile 坐标 `(row, col)` 转成字符串如 `"D2"`
4. 组装 `settings` 和 `actions`，输出 JSON

### 5.3 Cost OCR

```python
area = _extract_cost_number_area(frame)
cost = analyze_time.get_cost(area.tobytes(), width, height)
```

使用 `tesserocr` + 自定义训练模型 `arknights_digit`。

### 5.4 输出格式

**文件**：`axis_<ts>.json` 或 `sample 1-7.json`

```json
{
  "settings": {
    "map_code": "1-7",
    "max_tick": 30,
    "wait_time1": 0.02,
    "wait_time2": 0.1,
    "wait_time3": 0.3,
    "bullet_threshold": 15.0,
    "frame_threshold": 2.0
  },
  "actions": [
    {
      "cost": 15,
      "tick": 0,
      "action_type": "部署",
      "oper": "斑点",
      "pos": "D2",
      "direction": "右"
    }
  ]
}
```

---

## 六、阶段 5：执行阶段

入口：`src/main.py`

### 6.1 轴加载

**文件**：`src/axis/json_loader.py`

读取 JSON axis，解析为 `Action` dataclass 列表。

```python
Action(
    cost=raw.get("cost"),
    tick=raw.get("tick"),
    action_type=ActionType.DEPLOY,
    oper=raw.get("oper"),
    pos=raw.get("pos"),
    direction=DirectionType.RIGHT,
)
```

### 6.2 轴执行

**文件**：`src/axis/axis_runner.py`

对每个 action：
1. `convert_position()`：把 `pos` 字符串转成 `(col, row)` tile 坐标
2. `transform_map_to_view()`：把 tile 投影到屏幕坐标（正视/侧视）
3. 调用 `perform_action()` 执行

### 6.3 动作执行

**文件**：`src/logic/perform_action.py`

#### 部署（DEPLOY）

```python
perform_deploy(action, is_paused)
```

1. 等待到目标时间附近（`bullet_threshold` 前进入子弹时间）
2. 暂停游戏
3. 用 `locate_avatar()` 在待部署区找干员头像（OpenCV 模板匹配）
4. 点击干员头像选中
5. 再次定位头像（选中后位置可能变化）
6. 拖拽到侧视投影坐标
7. 如果有方向，做方向拖拽
8. 检查实际执行时间是否与目标一致

#### 技能/撤退（SKILL/RETREAT）

```python
perform_skill_or_retreat(action, is_paused)
```

1. 等待到目标时间
2. 点击干员在地图上的投影位置（选中）
3. 点击技能/撤退按钮

### 6.4 时间同步

**文件**：`src/logic/analyze_time.py`

实时获取游戏时间：

```python
def get_game_time() -> GameTime:
    cost_area_img = capture_game_window(ratio=COST_AREA_RATIO)
    tick = detector.detect_tick(...) or legacy_white_pixel(cost_area_img)
    cost = get_cost(cost_number_area)
    return GameTime(cost, tick)
```

时间基准是费用条像素宽度（tick）+ 费用数字 OCR（cost）。

---

## 七、数据流与文件格式

### 7.1 录制产出

```
recordings/
├── recording_20260620_114150.mp4          # 游戏画面视频
├── recording_20260620_114150_timestamps.json  # 帧时间戳 + 预计算 tick
├── actions_20260620_114150.json           # 鼠标动作 + avatar patch 路径
└── patches_20260620_114150/               # 拖拽时的头像 patch
    ├── avatar_patch_1.234000.png
    └── ...
```

### 7.2 timestamps.json 结构

```json
{
  "frame_timestamps": [0.0, 0.033, 0.066, ...],
  "frame_ticks": [
    {"frame_id": 0, "timestamp": 0.0, "tick": 0},
    {"frame_id": 1, "timestamp": 0.033, "tick": 1},
    ...
  ]
}
```

### 7.3 analysis.json 结构

```json
{
  "metadata": {
    "video_path": "...",
    "timestamps_path": "...",
    "scanned_frames": 1350,
    "ticks_per_cycle": 30,
    "tick_anomalies": [...]
  },
  "frames": [
    {
      "frame_id": 0,
      "timestamp": 0.0,
      "tick": 0,
      "cycle": 0,
      "total_elapsed_frames": 0,
      "paused": false
    }
  ]
}
```

### 7.4 actions.json 结构

```json
{
  "start_ts": 1234567890.123,
  "duration": 45.2,
  "action_count": 12,
  "actions": [
    {
      "type": "drag",
      "start_ts": 1.234,
      "end_ts": 1.567,
      "start_ratio": {"x": 0.12, "y": 0.85},
      "end_ratio": {"x": 0.45, "y": 0.42},
      "avatar_patch": "patches_.../avatar_patch_1.234000.png",
      "raw_events": [...]
    }
  ]
}
```

---

## 八、关键设计决策

### 8.1 为什么预计算 tick？

因为 H.264 压缩会模糊费用条边缘，导致离线重新检测 tick 出现抖动。录制时直接对原始帧检测，精度最高。

### 8.2 为什么用全局鼠标钩子？

MuMu 模拟器内的鼠标事件需要先经过 Windows 输入层，用 `pynput` 全局钩子可以捕获真实屏幕坐标，再通过 `CoordinateMapper` 映射回游戏窗口比例。

### 8.3 为什么头像 patch 要等鼠标离开待部署区才保存？

拖拽开始时鼠标光标会遮挡头像；当鼠标离开待部署区向上移动时，原槽位不再被光标遮挡，此时保存的 patch 最干净。

### 8.4 为什么方向判断用菱形区域？

明日方舟部署后的方向选择 UI 是一个以目标 tile 为中心的菱形（45° 旋转正方形），在屏幕投影中会随视角变化。用 tile 空间定义菱形，再投影到屏幕，比硬编码屏幕区域更鲁棒。

---

## 九、当前限制

| 限制 | 说明 | 可能的改进 |
|------|------|-----------|
| 仅支持 MuMu12 | 截图和输入都依赖 MuMu | 抽象 capture/input 层，支持 PC 客户端/ADB |
| 硬编码 ROI | 撤退/技能按钮区域、费用条区域都是固定比例 | 基于分辨率校准或图像识别动态定位 |
| 不能识别场上单位 | 部署/技能/撤退依赖几何投影 | 增加场上单位视觉校验 |
| 方向识别依赖后续拖拽 | 如果玩家点按方向 UI 而非拖拽会识别失败 | 同时支持点击方向 UI 的识别 |
| Cost OCR 依赖 tesserocr | 环境部署较重 | 使用 MAA OCR 或其他轻量方案 |
| 录制时不能识别关卡 | 需要手动指定 map_code | 增加关卡名 OCR |
| 暂停状态依赖 tick | 子弹时间下 tick 卡住，需要启发式修正 | 结合画面暂停检测做更精确判断 |

---

## 十、移植到 AAO 时的对应关系

| prts-plus 模块 | AAO 对应位置 | 移植建议 |
|---------------|-------------|---------|
| `recorder/video_recorder.py` | 新建 `aao/recorder/` | 复用，但改用 MAA `Win32Controller` 截图 |
| `src/input/mouse_listener.py` | 新建 | 复用，但过滤 `UnityWndClass` 窗口 |
| `recorder/avatar_patch_recorder.py` | 新建 | 复用，ROI 改成 AAO 的待部署区比例 |
| `recorder/offline_scanner.py` | 新建 | 复用 tick 状态机，费用条检测可换 AAO 的 |
| `recorder/action_recognizer.py` | 新建 | 复用，地图投影用 `aao/core/geometry/view.py` |
| `recorder/axis_writer.py` | `aao/timeline/timeline_writer.py` | 输出 AAO timeline 格式 |
| `src/frame/calibration.py` | `aao/core/timing/calibration.py` | 二选一或融合 |
| `src/logic/perform_action.py` | AAO 的 `custom/action/executor.py` | 不复用，AAO 已有更完善的执行器 |

---

## 十一、总结

prts-plus 的核心价值在于构建了一条**从录制到可执行轴的自动化流水线**：

1. **录制**：同步捕获视频、鼠标、tick、头像 patch
2. **离线分析**：把 tick 重建成时间线，把鼠标动作对齐到帧
3. **语义识别**：把 click/drag 翻译成 deploy/skill/retreat
4. **轴生成**：输出带 cost/tick 的 JSON axis
5. **执行**：按时间轴自动操作游戏

这套流程中，**录制-分析-识别-生成** 部分是最有价值的移植资产；**执行层** 则可以直接复用 AAO 已有的更成熟的实现。

---

## 十二、去除录屏的轻量化改造方案

当前 prts-plus 保存完整 MP4 主要是为了 Cost OCR 和调试可视化。实际上，tick 在录制时已经预计算，avatar patch 也是录制时预采集，完整视频并不是生成轴的必需输入。

如果目标平台改为 AAO/MaaFramework，可以进一步去掉 **视频录屏** 和 **avatar patch 预采集**，直接利用 MAA 已有的识别能力。

### 改造目标

- 不保存完整 MP4
- 不保存 avatar patch
- 录制时只保留：鼠标事件 + 关键帧 + tick/cost 时间线
- 分析时直接调用 MAA 的识别接口

### 新数据流

```
录制中：
  截图 → MAA 费用条识别（tick）+ OCR cost
  鼠标事件 → ActionRecorder 聚合为 click/drag
  每个动作发生时 → 保存一张关键帧（可选）

录制结束：
  用 MAA 识别每个 deploy 拖拽：
    - 拖拽起点区域 → MAA DetectSlots + MatchAvatar / OCR 识别干员
    - 拖拽终点 → 投影到地图 tile
    - 方向拖拽 → 推断朝向
  用已记录的 cost/tick 回填每个动作
  输出 JSON axis / AAO timeline
```

### 具体替换点

| 原 prts-plus 组件 | 改造方式 |
|------------------|---------|
| `recorder/video_recorder.py` | **删除**。不需要完整视频 |
| `recorder/avatar_patch_recorder.py` | **删除**。不预采集 patch |
| `src/logic/locate_avatar.py` | **替换为 AAO 的 `aao/core/avatar.py`**。用 MAA DetectSlots + OCR 自学习识别干员 |
| `recorder/axis_writer.py` 中的 `_VideoFrameProvider` | **删除**。cost 在录制时直接 OCR 并记录 |
| `recorder/offline_scanner.py` 的视频解码 fallback | **删除**。只使用预计算 tick |
| `recorder/action_recognizer.py` 中的 `AvatarMatcher.match_patch()` | **替换为 `locate_oper()`**。调用 MAA 接口直接识别当前画面 |

### 录制时需要新增的能力

1. **实时 Cost OCR**
   - 每帧或每几帧对费用数字区域做一次 OCR
   - 保存 `(timestamp, tick, cost)` 三元组
   - 可以直接复用 AAO 已有的 OCR 模型，或 MAA 的 OCR pipeline

2. **动作发生时保存关键帧**
   - 在 `mousedown` / `mouseup` 时保存当前游戏画面
   - 仅用于 MAA 识别干员名，不用于完整回放
   - 关键帧数量极少（一局几十张），可以大大降低存储

3. **用 MAA 替代自研识别**
   - 干员槽位检测：`DetectSlots`（TemplateMatch `BattleOpersFlag.png`）
   - 干员头像匹配：`MatchAvatar` + 缓存
   - 干员名 OCR：`OcrOperName`
   - 暂停验证：`BattlePaused`
   - 漏怪检测：`Farm@LeakDetect`

### 优势

| 方面 | 收益 |
|------|------|
| 存储 | 不需要 MP4，一局只需几十张关键帧 |
| 速度 | 分析时不需要解码视频，秒级出轴 |
| 识别准确率 | MAA 的 OCR + 模板匹配比 tesserocr 自训练模型更稳定 |
| 维护成本 | 不需要维护 `arknights_digit.traineddata` 和头像模板库 |
| 跨平台 | 只要 MAA 控制器支持，PC/模拟器都能用 |

### 限制

- 录制时 CPU 开销略增（实时 Cost OCR）
- 失去完整战斗回放能力
- 需要 MAA 环境（对 AAO 来说天然满足）

### 最小改造路径

1. 在 `record_actions.py` 中去掉 `VideoRecorder` 和 `AvatarPatchRecorder`
2. 增加实时 cost OCR，写入 timestamps
3. 在 `axis_writer.py` 中直接读 timestamps 的 cost，不再从视频取帧
4. 在 `action_recognizer.py` 中，deploy 干员识别改为调用 `aao.core.avatar.locate_oper()` 或等价的 MAA 接口
5. 删除 `offline_scanner.py` 的视频解码 fallback 代码

改造后，录制 → 出轴的延迟可以从分钟级降到 **秒级**，整个系统也更贴近 AAO 的 MAA 架构。
