# Step 8 接手 Prompt

> 直接复制以下内容给新 agent，用于继续推进 prts-plus 改造项目。

---

## 项目背景

你正在继续开发 `C:\Users\assert\Downloads\prts-plus-main`。

项目目标：把明日方舟自动轴工具 `prts-plus` 从 **Excel 宏驱动** 改造为 **JSON 轴 + CLI/UI 驱动**，形成“录制 → 离线分析 → 生成轴 → 执行”的闭环，并集成 `ArknightsCostBarRuler` 的帧检测与悬浮窗 UI。

请先阅读项目内的 handoff 索引：

```
docs/handoff/README.md
docs/handoff/prts-plus-handoff.md
docs/handoff/cuddly-pondering-fox-handoff.md
docs/handoff/handoff_step6.md
docs/handoff/handoff_step7.md
```

以及顶层计划：

```
C:\Users\assert\.claude\plans\cuddly-pondering-fox.md
```

## 当前进度

Step 0–7 已完成并验证：

- Step 0：JSON 轴 / CLI 入口（`--axis`、`AxisRunner`）
- Step 1：MuMu DLL 截图层
- Step 2：费用条校准（`calibration/*.json`）
- Step 3：视频录制（`recorder/video_recorder.py`）
- Step 4：鼠标监听 + 坐标转换（`src/input/`）
- Step 5：地图格子识别（`src/logic/calc_view.py`）
- Step 6：实时帧检测 + 悬浮 Overlay UI（`src/app.py` + `src/ui/overlay.py`）
- Step 7：离线费用条扫描（`recorder/offline_scanner.py` + `scripts/analyze_recording.py`）

**你的任务：Step 8 JSON 轴生成。**

## Step 8 目标

基于 Step 7 的离线分析结果和录制时的鼠标动作，生成可直接执行的 JSON axis（类似 `sample 1-7.json`），并补全暂停识别、单位元数据等前置能力。

## 需要实现的内容（按 `cuddly-pondering-fox.md` 原计划）

### 1. 暂停识别 `is_paused(frame)`

位置建议：`src/frame/pause_detector.py` 或 `recorder/vision.py`

- 输入：PIL RGB / numpy BGR 帧（1280×720）
- 输出：`bool`
- 实现思路（原计划）：
  - ROI 取屏幕中心区域
  - 首选 OCR 识别 "PAUSE" / "暂停中"（已存在 `tesserocr` + `arknights_digit` 模型）
  - fallback：中心区域亮度显著低于非暂停帧平均值，或检测暂停 UI 高亮连通域
- 注意：不要破坏 `AnalysisWorker` / `OfflineScanner` 的现有接口；建议把 `is_paused` 作为可选 detector 注入，或在扫描阶段调用。

### 2. 语义识别 `recorder/action_recognizer.py`

把 `actions_*.json` 中的 click/drag 识别为具体动作类型：

| 鼠标模式 | 动作类型 | 判断依据 |
|----------|----------|----------|
| drag（起点在待部署区，终点在地图区） | 部署 | 拖拽是从干员栏放到地图上 |
| click（点在已部署干员身上或技能圈） | 技能 | 短点击地图上已部署单位 |
| click（点在撤退按钮附近或干员头像上） | 撤退 | 点击撤退 UI |
| 其他 | 未知/忽略 | 如点击暂停、倍速、空地点 |

需要读取的已有模块：
- `src/input/action_recorder.py`：`RecordedAction` 结构
- `src/logic/calc_view.py`：`transform_view_to_map(level, ratio_pos, side)` 反推 tile
- `src/config.py`：`GameRatioConfig` 中的 `OPERATOR_AREA_RATIO`、`RETREAT_RATIO`、`SKILL_RATIO`、`LAST_OPER_RATIO`

### 3. 干员识别（部署动作）

部署 drag 的起点在待部署区，需要识别是哪个干员：

- 使用 `src/cache.py`：`load_avatars(oper_name)` / `get_avatars(oper_name)` 做头像模板匹配
- 拖拽起点的 ratio 坐标对应待部署区头像位置
- 返回 oper 名称；如果匹配失败，保留 raw 坐标并标记 "unknown"

### 4. 单位元数据 `resource/unit_metadata.json`

新建 `scripts/generate_unit_metadata.py`：

- 读取 `character_table.json` 和 `range_table.json`
- 对每个可部署单位生成：
  - `char_id`
  - `name`
  - `profession`（如 SNIPER、GUARD、TOKEN 等）
  - `sub_profession_id`
  - `needs_direction`: bool — 根据攻击范围和职业判断（如召唤物 / 援卫 / 快活通常不需要方向；常规地面/高台通常需要）
- 输出 `resource/unit_metadata.json`

修改 `src/cache.py`：
- 新增 `load_unit_metadata()` / `get_unit_metadata(oper_name)`
- 部署时根据 `needs_direction` 决定 axis 是否必须包含 direction

### 5. JSON 轴生成 `recorder/axis_writer.py`

输入：
- `recording_analysis.json`（离线扫描结果）
- `actions_*.json`（带 `game_time` 标注）
- 关卡信息（`map_code` 或 `map_name`）

输出：`axis_<ts>.json`，结构同 `sample 1-7.json`：

```json
{
  "settings": {
    "map_code": "1-7",
    "max_tick": 30,
    "wait_time1": 0.02,
    "wait_time2": 0.1,
    "wait_time3": 0.3,
    "bullet_threshold": 15,
    "frame_threshold": 2
  },
  "actions": [
    {
      "cost": 10,
      "tick": 5,
      "action_type": "部署",
      "oper": "斑点",
      "pos": "D2",
      "direction": "右"
    }
  ]
}
```

字段映射：
- `cost`: 从录制时费用条 OCR 或离线扫描的 tick 反推（可用 `src/logic/analyze_time.py` 的 `get_cost`，或简单用 `tick` 近似）
- `tick`: 来自 `game_time.tick`
- `action_type`: "部署" / "技能" / "撤退"
- `oper`: 部署时从头像匹配得到；技能/撤退时从已记录位置反查
- `pos`: 部署目标 tile，如 "D2"；技能/撤退可省略或使用目标 tile
- `direction`: 部署时根据单位元数据 `needs_direction` 决定；若需要但无法识别，默认 "右"

### 6. CLI 脚本 `scripts/generate_axis.py`

用法建议：

```bash
.venv\Scripts\python scripts/generate_axis.py \
  --analysis recordings/recording_<ts>_analysis.json \
  --actions recordings/actions_<ts>.json \
  --map-code 1-7 \
  --output axis_<ts>.json
```

或自动使用最新录制：

```bash
.venv\Scripts\python scripts/generate_axis.py --map-code 1-7
```

## 关键现有文件

| 文件 | 用途 |
|------|------|
| `sample 1-7.json` | JSON axis 输出格式参考 |
| `src/axis/json_loader.py` | axis JSON 加载器，含 action/direction 映射 |
| `src/axis/axis_runner.py` | axis 执行器 |
| `src/logic/action.py` | `Action` / `ActionType` / `DirectionType` |
| `src/logic/perform_action.py` | 实际执行部署/技能/撤退 |
| `src/logic/calc_view.py` | 视图 ratio → tile 逆变换 |
| `src/logic/convert_pos.py` | tile 字符串（如 D2）↔ (row, col) |
| `src/logic/analyze_time.py` | 实时 tick/cost OCR |
| `src/cache.py` | 加载 operator_mapping、头像、地图数据 |
| `character_table.json` | 干员元数据 |
| `resource/operator_mapping.json` | 中文名 → char_id |

## 已知限制与风险

- **暂停识别当前是占位**：Step 7 的 `TickStateTracker.paused` 只在费用条检测失败时为 `True`。Step 8 需要真正识别暂停 UI。
- **头像匹配精度**：待部署区头像可能重叠、被遮挡，需要设置匹配阈值和 fallback。
- **视角问题**：`transform_view_to_map` 需要知道当前是正视图还是侧视图。Step 6 的 overlay 视角按钮是占位符，Step 8 需要确定当前视角（可默认正视图，或从录制画面特征推断）。
- **撤退/技能目标识别**：技能/撤退需要知道点击的是哪个已部署干员。建议维护一个 `oper -> tile_pos` 映射，部署时记录，后续操作按 oper 查找。

## 验证方式

1. 单元测试：

```bash
.venv\Scripts\python -m unittest tests.test_action_recognizer tests.test_axis_writer -v
```

2. 用已有录制生成 axis：

```bash
# 先确保有 analysis 文件
.venv\Scripts\python scripts/analyze_recording.py

# 生成 axis
.venv\Scripts\python scripts/generate_axis.py --map-code 1-7

# 验证 axis 可被加载
.venv\Scripts\python -c "from src.axis.json_loader import load_axis_from_json; load_axis_from_json('axis_<ts>.json')"
```

3. 实机验证（可选）：

```bash
.venv\Scripts\python run.py --axis axis_<ts>.json --autoenter
```

## 建议的拆分顺序

1. `resource/unit_metadata.json` 生成 + `src/cache.py` 加载
2. 暂停识别 `is_paused(frame)`
3. 动作语义识别 `recorder/action_recognizer.py`
4. 干员头像匹配集成
5. JSON axis 输出 `recorder/axis_writer.py`
6. CLI `scripts/generate_axis.py`
7. 单元测试 + handoff 文档 `docs/handoff/handoff_step8.md`

## 不要做的事

- 不要改回父/子窗口方案；悬浮窗使用单根 `ttk.Window`。
- 初始状态不要走 `ui_queue`；用 `overlay.set_initial_state(...)`。
- 不要删除 Excel 兼容路径；JSON 轴是新增入口，Excel 仍要可用。
- 不要重写 `AnalysisWorker` 的线程模型，除非必要。

---

完成后请更新：

- `docs/handoff/handoff_step8.md`
- `docs/handoff/README.md` 中的进度表
- 新增/修改的单元测试
