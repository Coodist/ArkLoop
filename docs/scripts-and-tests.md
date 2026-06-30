# prts-plus 脚本与测试速查手册

本目录整理了 `prts-plus` 项目中所有**测试、验证、开发辅助脚本**和**单元测试**，方便后续复用和排查问题。

> 项目根目录：`C:\Users\assert\Downloads\prts-plus-main`
> 运行环境：Windows + Python 3.11（推荐用项目自带的 `.venv`）
> 目标平台：MuMu模拟器12 + 明日方舟（16:9 分辨率）

---

## 1. 环境准备

所有脚本建议通过项目虚拟环境运行：

```bash
.venv\Scripts\python scripts/xxx.py
```

首次使用前确保依赖已安装：

```bash
# 完整依赖（含 tesserocr，需要 Tesseract 环境）
.venv\Scripts\python -m pip install -r requirements.txt

# 如果 tesserocr 安装困难，可用无 tesserocr 版本（部分 OCR 功能不可用）
.venv\Scripts\python -m pip install -r requirements_no_tesserocr.txt
```

> 注意：许多脚本依赖 `MuMu模拟器12` 正在运行且游戏窗口可见。

---

## 2. 脚本总览（按用途分类）

| 类别 | 脚本 | 是否需要模拟器 | 主要用途 |
|------|------|---------------|----------|
| 截图/捕获 | `test_mumu_capture.py` | 是 | 测试 MuMu DLL / Win32 截图速度 |
| 截图/捕获 | `test_capture_fps.py` | 是 | 测量实际截图帧率 |
| 费用条校准 | `calibrate.py` | 是 | 交互式费用条校准 |
| 费用条校准 | `verify_calibration.py` | 是 | 实时验证校准结果 |
| 费用条校准 | `test_calibration_logic.py` | 否 | 离线合成测试校准算法 |
| 录制 | `record_actions.py` | 是 | 录制视频+鼠标+tick+头像patch |
| 录制 | `record_test.py` | 是 | 仅录制游戏窗口视频 |
| 录制 | `test_recorder_logic.py` | 否 | 离线测试视频录制器 |
| 输入/鼠标 | `test_input_logic.py` | 否 | 离线测试鼠标事件聚合 |
| 输入/鼠标 | `debug_mouse_events.py` | 是 | 调试全局鼠标钩子事件 |
| 输入/鼠标 | `verify_click_positions.py` | 是 | 验证屏幕坐标到游戏比例映射 |
| 地图/UI | `verify_view_to_map.py` | 是 | 验证视图坐标到地图tile的转换 |
| 地图/UI | `visualize_ui_regions.py` | 是 | 可视化检测区域（撤退/技能/方向等） |
| 识别 | `verify_avatar_patch_capture.py` | 是 | 验证头像patch捕获事件驱动逻辑 |
| 识别 | `test_avatar_cursor_occlusion.py` | 否 | 合成测试鼠标遮挡对头像匹配的影响 |
| 识别 | `test_avatar_cursor_occlusion2.py` | 否 | 带噪声的遮挡合成测试 |
| 识别 | `test_action_state_machine.py` | 是 | 实时测试动作语义识别状态机 |
| 识别 | `debug_recognition.py` | 否 | 调试已录制动作的语义识别结果 |
| 离线分析 | `analyze_recording.py` | 否 | 离线扫描录制视频重建tick时间线 |
| 离线分析 | `verify_step7.py` | 否 | Step 7 完整验证流程 |
| 轴生成 | `generate_axis.py` | 否 | 从分析结果+动作生成可执行JSON轴 |
| 数据资源 | `process_battle_data.py` | 否 | 生成 operator_mapping.json |
| 数据资源 | `process_overview.py` | 否 | 生成 level_code/name_mapping.json |
| 数据资源 | `generate_unit_metadata.py` | 否 | 从游戏数据表生成 unit_metadata.json |
| Excel转换 | `convert_excel_to_json.py` | 否 | 将旧版Excel轴转为JSON轴 |
| UI | `run_overlay.py` | 是 | 启动实时悬浮窗显示tick |

---

## 3. 截图与捕获测试

### 3.1 `scripts/test_mumu_capture.py` — 测试 MuMu DLL / Win32 截图

用途：验证截图控制器能否正常连接，并测量截图延迟。

```bash
# 测试 MuMu DLL 截图（推荐，快且稳定）
.venv\Scripts\python scripts/test_mumu_capture.py --path "D:\Program Files\Netease\MuMu Player 12" --instance 0

# 测试 Win32 BitBlt 回退
.venv\Scripts\python scripts/test_mumu_capture.py --path "..." --win32
```

输出示例：
- 平均截图耗时（ms/帧）
- 估算最大 FPS
- 最后保存的截图 `mumu_capture_test.jpg` / `win32_capture_test.jpg`

### 3.2 `scripts/test_capture_fps.py` — 测量实际截图帧率

用途：长时间测量当前配置下能达到的截图帧率。

```bash
.venv\Scripts\python scripts/test_capture_fps.py --duration 30
```

---

## 4. 费用条校准与验证

费用条校准是帧级操作的基础。必须先校准，后续的录制/识别/执行才能正常工作。

### 4.1 `scripts/calibrate.py` — 交互式校准

用途：录制费用条若干个完整循环，生成校准文件 `calibration/default_*.json`。

```bash
.venv\Scripts\python scripts/calibrate.py
```

前置条件：
- MuMu 模拟器已打开
- 已进入任意关卡（费用条在走动）
- 游戏窗口可见

输出：`calibration/default_1280x720.json`

### 4.2 `scripts/verify_calibration.py` — 实时验证校准

用途：校准后实时读取当前 tick，确认校准数据正确。

```bash
.venv\Scripts\python scripts/verify_calibration.py
```

按 `Ctrl+C` 停止。如果输出 tick 能跟随费用条正常递增/归零，说明校准成功。

### 4.3 `scripts/test_calibration_logic.py` — 离线校准算法测试

用途：**不需要模拟器**，用 Pillow 合成假费用条，验证校准/检测逻辑。

```bash
.venv\Scripts\python scripts/test_calibration_logic.py
```

覆盖的测试点：
- ROI 计算和填充宽度检测
- 多周期聚类校准
- 校准文件保存/加载
- 检测器查表
- `GameTime.apply_calibration`

---

## 5. 录制相关脚本

### 5.1 `scripts/record_actions.py` — 完整录制

用途：同步录制游戏视频、鼠标动作、每帧 tick、部署头像 patch。

```bash
# 录制 10 秒
.venv\Scripts\python scripts/record_actions.py --duration 10

# 不录视频，只保存 timestamps + actions + patches
.venv\Scripts\python scripts/record_actions.py --duration 10 --no-video

# 录制完整鼠标轨迹（可能卡顿）
.venv\Scripts\python scripts/record_actions.py --duration 10 --record-moves
```

输出（在 `recordings/` 目录）：
- `recording_<ts>.mp4`
- `recording_<ts>_timestamps.json`
- `actions_<ts>.json`
- `patches_<ts>/avatar_patch_*.png`

### 5.2 `scripts/record_test.py` — 仅录视频

用途：快速验证视频录制模块是否工作。

```bash
.venv\Scripts\python scripts/record_test.py --duration 10
```

### 5.3 `scripts/test_recorder_logic.py` — 离线测试视频录制器

用途：合成帧测试 FFmpeg 输出是否有效。

```bash
.venv\Scripts\python scripts/test_recorder_logic.py
```

---

## 6. 输入/鼠标相关脚本

### 6.1 `scripts/test_input_logic.py` — 离线测试鼠标事件聚合

用途：测试 `ActionRecorder` 将原始 `mousedown/mouseup` 聚合成 `click/drag` 的逻辑。

```bash
.venv\Scripts\python scripts/test_input_logic.py
```

### 6.2 `scripts/debug_mouse_events.py` — 调试全局鼠标钩子

用途：确认 MuMu 在前台时，全局鼠标钩子能正确收到点击/拖拽事件。

```bash
.venv\Scripts\python scripts/debug_mouse_events.py
```

### 6.3 `scripts/verify_click_positions.py` — 验证坐标映射

用途：点击 MuMu 游戏区域的 6 个固定点，验证屏幕坐标→游戏比例坐标的映射。

```bash
.venv\Scripts\python scripts/verify_click_positions.py
```

---

## 7. 地图/UI 验证脚本

### 7.1 `scripts/verify_view_to_map.py` — 验证视图→地图 tile 转换

用途：在指定关卡中点击地图 tile，打印对应的 `(row, col)`。

```bash
.venv\Scripts\python scripts/verify_view_to_map.py --map-code 1-7
.venv\Scripts\python scripts/verify_view_to_map.py --map-code 1-7 --side
```

### 7.2 `scripts/visualize_ui_regions.py` — 可视化检测区域

用途：截图并在图像上叠加绘制：
- 待部署区（绿色矩形）
- 撤退按钮区域（红色多边形）
- 技能按钮区域（蓝色多边形）
- 某 tile 的方向拖拽菱形（橙色）
- 暂停/倍速/开始按钮（彩色圆点）
- 3D 投影后的 tile 网格

```bash
.venv\Scripts\python scripts/visualize_ui_regions.py --map-code 1-7 --tile 3,8
```

输出：`recordings/ui_regions_overlay.png`

---

## 8. 动作识别相关脚本

### 8.1 `scripts/verify_avatar_patch_capture.py` — 验证头像 patch 捕获

用途：在 MuMu 中执行部署拖拽，验证事件驱动的头像 patch 捕获是否正常工作。

```bash
.venv\Scripts\python scripts/verify_avatar_patch_capture.py --duration 10
```

### 8.2 `scripts/test_avatar_cursor_occlusion.py` — 鼠标遮挡合成测试

用途：评估鼠标指针遮挡头像时，模板匹配分数下降多少。

```bash
.venv\Scripts\python scripts/test_avatar_cursor_occlusion.py
```

### 8.3 `scripts/test_avatar_cursor_occlusion2.py` — 带噪声遮挡测试

用途：在更真实的环境（边框、噪声）下评估遮挡影响。

```bash
.venv\Scripts\python scripts/test_avatar_cursor_occlusion2.py
```

### 8.4 `scripts/test_action_state_machine.py` — 实时识别状态机测试

用途：不需要真实头像库，用卡槽索引代替干员名，实时测试视图切换/选中/部署/方向/技能/撤退识别。

```bash
.venv\Scripts\python scripts/test_action_state_machine.py --map-code 1-7
```

### 8.5 `scripts/debug_recognition.py` — 调试已录制动作识别

用途：加载最新录制的 `analysis.json` + `actions.json`，打印每个动作的识别结果和失败原因。

```bash
.venv\Scripts\python scripts/debug_recognition.py --map-code 1-7
```

---

## 9. 离线分析与轴生成

### 9.1 `scripts/analyze_recording.py` — 离线扫描录制视频

用途：从 `recordings/` 中读取视频+timestamps，重建费用条 tick 时间线。

```bash
# 自动使用最新录制
.venv\Scripts\python scripts/analyze_recording.py

# 指定文件
.venv\Scripts\python scripts/analyze_recording.py \
    --video recordings/recording_20260619_123456.mp4 \
    --timestamps recordings/recording_20260619_123456_timestamps.json \
    --output analysis/recording_20260619_123456_analysis.json

# 启用暂停检测叠加
.venv\Scripts\python scripts/analyze_recording.py --detect-pause
```

### 9.2 `scripts/verify_step7.py` — Step 7 完整验证

用途：一键跑通 Step 7 的单元测试、离线扫描、输出结构校验。

```bash
.venv\Scripts\python scripts/verify_step7.py
```

步骤：
1. 运行 `tests.test_offline_scanner` 和 `tests.test_detector_worker`
2. 检查 `recordings/` 是否有最新录制对
3. 运行 `analyze_recording.py`
4. 校验输出 JSON 结构

### 9.3 `scripts/generate_axis.py` — 生成可执行 JSON 轴

用途：将 `analysis.json` + `actions.json` 转换为 `src/main.py` 能执行的 JSON 轴。

```bash
# 自动使用 recordings/ 下最新的一对分析+动作文件
.venv\Scripts\python scripts/generate_axis.py --map-code 1-7

# 指定文件
.venv\Scripts\python scripts/generate_axis.py \
    --analysis recordings/recording_<ts>_analysis.json \
    --actions recordings/actions_<ts>.json \
    --map-code 1-7 \
    --output axis_<ts>.json
```

---

## 10. 数据与资源处理脚本

### 10.1 `script/process_battle_data.py`

用途：从 `resource/battle_data.json` 生成 `resource/operator_mapping.json`（干员名→文件名）。

```bash
.venv\Scripts\python script/process_battle_data.py
```

### 10.2 `script/process_overview.py`

用途：从 `resource/map/overview.json` 生成：
- `resource/level_code_mapping.json`
- `resource/level_name_mapping.json`

```bash
.venv\Scripts\python script/process_overview.py
```

### 10.3 `scripts/generate_unit_metadata.py`

用途：从 `character_table.json` + `range_table.json` 生成 `new_resource/unit_metadata.json`。

```bash
.venv\Scripts\python scripts/generate_unit_metadata.py \
    --character-table "C:\...\character_table.json" \
    --range-table "C:\...\range_table.json" \
    --output new_resource/unit_metadata.json
```

---

## 11. Excel/JSON 转换

### 11.1 `scripts/convert_excel_to_json.py`

用途：将旧版 `.xlsm` Excel 轴转换为新版 JSON 轴。

```bash
.venv\Scripts\python scripts/convert_excel_to_json.py "sample 1-7.xlsm"

# 指定输出路径
.venv\Scripts\python scripts/convert_excel_to_json.py "sample 1-7.xlsm" -o "sample-1-7.json"
```

---

## 12. UI 工具

### 12.1 `scripts/run_overlay.py` — 实时 tick 悬浮窗

用途：在游戏窗口上方显示当前费用条 tick。

```bash
.venv\Scripts\python scripts/run_overlay.py
```

首次运行若找不到校准数据，点击悬浮窗上的 **Calibrate** 按钮即可。

---

## 13. 单元测试（tests/ 目录）

所有单元测试都**不需要模拟器**，可直接运行：

```bash
# 运行全部测试
.venv\Scripts\python -m unittest discover -v tests

# 运行单个测试
.venv\Scripts\python -m unittest tests.test_calc_view -v
.venv\Scripts\python -m unittest tests.test_offline_scanner -v
.venv\Scripts\python -m unittest tests.test_action_recognizer -v
.venv\Scripts\python -m unittest tests.test_avatar_patch_recorder -v
.venv\Scripts\python -m unittest tests.test_axis_writer -v
.venv\Scripts\python -m unittest tests.test_pause_detector -v
.venv\Scripts\python -m unittest tests.test_detector_worker -v
```

| 测试文件 | 测试内容 |
|----------|----------|
| `tests/test_calc_view.py` | 地图↔视图坐标正反向转换 |
| `tests/test_offline_scanner.py` | 离线扫描器、TickStateTracker、异常检测、预计算 tick 回退 |
| `tests/test_action_recognizer.py` | 部署/方向/技能/撤退识别逻辑 |
| `tests/test_avatar_patch_recorder.py` | 头像 patch 捕获事件驱动逻辑 |
| `tests/test_axis_writer.py` | JSON 轴生成器 |
| `tests/test_pause_detector.py` | 暂停检测（OCR + 亮度启发式 + 卡顿检测） |
| `tests/test_detector_worker.py` | `AnalysisWorker` 状态机（cycle 计数、暂停状态） |

---

## 14. 常用工作流

### 工作流 A：从零开始校准并验证

```bash
.venv\Scripts\python scripts/calibrate.py
.venv\Scripts\python scripts/verify_calibration.py
```

### 工作流 B：录制一次操作并生成可执行轴

```bash
# 1. 录制
.venv\Scripts\python scripts/record_actions.py --duration 30

# 2. 离线分析
.venv\Scripts\python scripts/analyze_recording.py

# 3. 生成 JSON 轴
.venv\Scripts\python scripts/generate_axis.py --map-code 1-7

# 4. 执行（需要 Excel 或命令行）
.venv\Scripts\python src/main.py --axis axis_<ts>.json --xlsm template.xlsm
```

### 工作流 C：只验证坐标和 UI 区域

```bash
.venv\Scripts\python scripts/verify_click_positions.py
.venv\Scripts\python scripts/verify_view_to_map.py --map-code 1-7
.venv\Scripts\python scripts/visualize_ui_regions.py --map-code 1-7 --tile 3,8
```

### 工作流 D：调试识别问题

```bash
# 先看鼠标事件有没有被正确捕获
.venv\Scripts\python scripts/debug_mouse_events.py

# 再看头像 patch 有没有正确保存
.venv\Scripts\python scripts/verify_avatar_patch_capture.py --duration 10

# 最后看为什么动作没被识别成部署/技能/撤退
.venv\Scripts\python scripts/debug_recognition.py --map-code 1-7
```

---

## 15. 故障排查速查

| 现象 | 排查脚本/命令 |
|------|--------------|
| 截图很慢/失败 | `scripts/test_mumu_capture.py`、`scripts/test_capture_fps.py` |
| tick 识别不准 | `scripts/verify_calibration.py`、`scripts/test_calibration_logic.py` |
| 录制后没有 actions | `scripts/debug_mouse_events.py`、`scripts/test_input_logic.py` |
| 坐标映射错误 | `scripts/verify_click_positions.py` |
| 地图 tile 识别错 | `scripts/verify_view_to_map.py`、`scripts/visualize_ui_regions.py` |
| 头像匹配失败 | `scripts/verify_avatar_patch_capture.py`、`scripts/test_avatar_cursor_occlusion.py` |
| 动作识别错误 | `scripts/debug_recognition.py`、`scripts/test_action_state_machine.py` |
| 离线扫描异常 | `scripts/verify_step7.py`、`tests.test_offline_scanner` |
| 找不到 calibration | `scripts/calibrate.py` 或检查 `calibration/` 目录 |

---

## 16. 文件位置索引

```
prts-plus-main/
├── scripts/                  # 交互式/验证/开发脚本
│   ├── calibrate.py
│   ├── verify_calibration.py
│   ├── test_calibration_logic.py
│   ├── record_actions.py
│   ├── record_test.py
│   ├── test_recorder_logic.py
│   ├── analyze_recording.py
│   ├── verify_step7.py
│   ├── generate_axis.py
│   ├── debug_recognition.py
│   ├── test_action_state_machine.py
│   ├── verify_avatar_patch_capture.py
│   ├── test_avatar_cursor_occlusion.py
│   ├── test_avatar_cursor_occlusion2.py
│   ├── verify_click_positions.py
│   ├── verify_view_to_map.py
│   ├── visualize_ui_regions.py
│   ├── debug_mouse_events.py
│   ├── test_input_logic.py
│   ├── test_mumu_capture.py
│   ├── test_capture_fps.py
│   ├── run_overlay.py
│   ├── convert_excel_to_json.py
│   └── generate_unit_metadata.py
├── tests/                    # unittest 单元测试
│   ├── test_calc_view.py
│   ├── test_offline_scanner.py
│   ├── test_action_recognizer.py
│   ├── test_avatar_patch_recorder.py
│   ├── test_axis_writer.py
│   ├── test_pause_detector.py
│   └── test_detector_worker.py
├── script/                   # 资源生成脚本（项目构建时运行）
│   ├── process_battle_data.py
│   └── process_overview.py
├── recorder/                 # 录制/识别/轴生成核心模块
├── src/frame/                # 费用条检测/校准/暂停检测
├── src/input/                # 鼠标监听/坐标映射
├── src/logic/                # 游戏时间/视图计算/动作执行
└── docs/                     # 文档目录
    ├── scripts-and-tests.md  # 本文件
    ├── recording-pipeline.md # 录制→生成轴完整流水线
    └── handoff/              # 各阶段 handoff 文档
```

---

## 17. 提示

- 大部分**带 `test_` 前缀的脚本**可以离线运行，适合 CI 或快速回归。
- 大部分**带 `verify_` 前缀的脚本**需要 MuMu 模拟器在前台运行，属于交互式验证。
- 运行前建议先确认 `.venv\Scripts\python` 是当前解释器，避免用错全局 Python。
- 如果脚本运行时提示找不到模块，先检查是否在项目根目录执行，以及 `sys.path` 是否包含项目根目录（脚本里已经做了处理）。
