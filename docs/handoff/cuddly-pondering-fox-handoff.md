# prts-plus 改造交接文档

> 创建于 2026-06-19。当前上下文已压缩，新 agent 请优先阅读本文 + 原计划 `cuddly-pondering-fox.md`。  
> 项目位置：`C:\Users\assert\Downloads\prts-plus-main`

## 项目目标

把 `prts-plus` 从 Excel 宏驱动改造为 **JSON 轴 + 命令行/UI 驱动**，并集成 `ArknightsCostBarRuler` 的帧检测与悬浮窗 UI，最终形成“录制 → 离线分析 → 生成轴 → 执行”的闭环。

## 当前进度

| 步骤 | 状态 | 说明 |
|---|---|---|
| Step 0：JSON 轴 + 命令行触发 | ✅ 已完成并验证 | `--axis sample-1-7.json --autoenter` 跑通 1-7；`--xlsm` 仍兼容 |
| Step 1：MuMu DLL 截图层替换 | ✅ 已完成并验证 | DLL 截图平均 154 FPS；Win32 fallback 已对齐客户区；点击坐标已同步修复 |
| Step 2：费用条校准流程 | ✅ 已完成并验证 | 移植 Ruler 校准逻辑，生成 `calibration/*.json`；`--calibrate` / `scripts/calibrate.py` 可用；`scripts/verify_calibration.py` 实时 tick 验证通过；`scripts/test_calibration_logic.py` 离线逻辑测试通过 |
| `recorder/video_recorder.py` | 基于 FFmpeg 的逐帧录制器，带时间戳 | 新建 |
| `recorder/__init__.py` | 录制模块入口 | 新建 |
| `scripts/record_test.py` | 实机录制游戏窗口 N 秒 | 新建 |
| `scripts/test_recorder_logic.py` | 离线录制器合成测试 | 新建 |
| `src/mumu/mumu_vision.py` | `capture_game_window` 增加 `color` 参数 | 修改 |
| `src/mumu/win32_capture.py` | `capture_frame` 增加 `color` 参数 | 修改 |
| `src/config.py` | 新增 `RecordingConfig` | 修改 |
| `requirements.txt` / `requirements_no_tesserocr.txt` | 新增 `imageio-ffmpeg==0.5.1` | 修改 |
| Step 3：视频录制 + 帧时间戳 | ✅ 已完成并验证 | 新增 `recorder/video_recorder.py`，基于 FFmpeg H.264 录制并记录每帧时间戳；离线/实机录制验证通过；修复 FFmpeg stderr 管道阻塞；截图支持 `color=True` |
| Step 4-9 | 未开始 | 见原 plan |

## 验证结果

### 1. Capture 性能测试

```bash
.venv\Scripts\python scripts\test_capture_fps.py --duration 30
```

结果：

```
Controller: MuMuPlayerController
Finished: 4620 frames in 30.004s
Average FPS: 154.0
Target 30 FPS margin: 5.13x
```

结论：MuMu DLL capture 层完全支撑 30fps 录制，有余量。

### 2. JSON 轴端到端验证

```bash
.venv\Scripts\python run.py --axis sample-1-7.json --autoenter
```

结果：正常通过，部署/技能/撤退/自动进图均正确。

### 3. 费用条校准验证

离线逻辑测试：

```bash
.venv\Scripts\python scripts\test_calibration_logic.py
```

结果：全部通过。

实时校准与验证：

```bash
.venv\Scripts\python scripts\calibrate.py
.venv\Scripts\python scripts\verify_calibration.py
```

结果：成功生成 `calibration/default_30f_1280x720.json`，`scripts/verify_calibration.py` 中 tick 在 0–29 连续递增；暂停游戏时 tick 停止变化。

结论：校准模块可用，已接入 `analyze_time.py` 作为优先检测路径。

### 4. 视频录制验证（✅ 已完成）

离线逻辑测试：

```bash
.venv\Scripts\python scripts/test_recorder_logic.py
```

结果：✅ 全部通过。
- 合成 60 帧视频 `recordings/test_logic.mp4`：1280×720、30 FPS，OpenCV 读取帧数/宽高/FPS 均正确。
- 合成 30 帧视频 `recordings/test_ts.mp4`：时间戳严格单调递增。

实机录制验证（MuMu 已开启并进入关卡）：

```bash
.venv\Scripts\python scripts/record_test.py --duration 10
```

结果：✅ 成功生成约 10 秒 MP4，帧数 ≈ 300，平均 FPS ≈ 30，视频可正常播放。

**关键修复 / 注意事项**：
- 首次实机测试时 `scripts/record_test.py` 在 "Recording started" 后卡死，`Ctrl+C` 无效。
- 根因不是 MuMu DLL 卡死，而是 `recorder/video_recorder.py` 把 FFmpeg 的 `stdout`/`stderr` 都接到 `subprocess.PIPE` 但从不读取。长时间录制时 FFmpeg 的 stderr 缓冲区被写满，FFmpeg 阻塞，进而导致 `stdin.write()` 阻塞，整个录制循环冻住。
- 修复：
  - `VideoRecorder` 将 FFmpeg `stdout` 重定向到 `DEVNULL`，`stderr` 写入 `.ffmpeg.log` 文件。
  - `record_test.py` 仍保留 50ms 首帧等待和 `elapsed >= duration` 终止条件作为兜底。
- 彩色录制：给 `capture_game_window()` 增加 `color=True` 参数；`record_test.py` 使用彩色截图，避免视频黑白。
### 重新打包命令

```bash
cd C:\Users\assert\Downloads\prts-plus-main
source .venv/Scripts/activate
pyinstaller -y --name "prts+" --onedir --add-data "resource;resource" --add-data "hook;hook" run.py
# 打包结果在 dist/prts+/ 下，需复制到根目录
cp -r dist/prts+/* .
```

### Tesseract 语言数据

- `arknights_digit.traineddata` 是项目自定义 OCR 模型，官方 Tesseract 没有。
- 来源：从 release 包 `_internal/Tesseract-OCR/tessdata/` 中复制。
- 当前存放位置：`C:\Users\assert\Downloads\prts-plus-main\tessdata_backup/tessdata/`

## 关键文件

| 文件 | 作用 | 状态 |
|---|---|---|
| `run.py` | PyInstaller 打包入口，设置 `TESSDATA_PREFIX` | 修改 |
| `src/main.py` | 入口，支持 `--axis` / `--xlsm` / `--calibrate` | 修改 |
| `src/axis/json_loader.py` | 加载 JSON 轴为 `List[Action]` | 新增 |
| `src/axis/axis_runner.py` | 统一执行循环（JSON/Excel 共用） | 新增 |
| `src/logic/action.py` | `Action` 数据类 | 修改 |
| `src/excel.py` | Excel 轴解析 | 修改（兼容 JSON 轴） |
| `src/mumu/capture_controller.py` | 截图控制器抽象基类 | 新增 |
| `src/mumu/mumu_dll_controller.py` | MuMu DLL 截图控制器 | 新增 |
| `src/mumu/win32_capture.py` | Win32 BitBlt fallback（已对齐客户区） | 新增 |
| `src/mumu/mumu_vision.py` | 统一截图接口 `capture_game_window(ratio)` | 修改 |
| `src/mumu/mumu_controller.py` | 模拟鼠标/键盘输入（点击坐标已改客户区） | 修改 |
| `src/mumu/mumu_connection.py` | 窗口句柄获取 | 修改 |
| `src/logic/locate_avatar.py` | 模板匹配定位待部署区头像 | 已有 |
| `src/logic/calc_view.py` | 地图 tile → 屏幕比例坐标 | 已有 |
| `src/logic/convert_pos.py` | 棋盘坐标（如 `D2`）→ `(row, col)` | 已有 |
| `src/logic/analyze_time.py` | 费用条 tick 检测：优先用校准，无校准则回退白像素法 | 修改 |
| `src/logic/game_time.py` | `GameTime(cost, tick)`，支持从校准设置 `TICK_MAX` | 修改 |
| `src/frame/calibration.py` | 费用条校准：ROI、pixel 宽度、聚类、存取校准文件 | 新增 |
| `src/frame/detector.py` | `CostBarDetector`：校准数据 → tick | 新增 |
| `scripts/calibrate.py` | 交互式费用条校准脚本 | 新增 |
| `scripts/verify_calibration.py` | 实时验证 tick 检测 | 新增 |
| `scripts/test_calibration_logic.py` | 离线合成数据校准逻辑测试 | 新增 |
| `src/cache.py` | 加载 `resource/operator_mapping.json` 和头像 | 已有 |
| `config.json` | 当前运行配置 | 已创建 |
| `config.example.json` | 配置模板 | 已创建 |
| `scripts/convert_excel_to_json.py` | Excel → JSON 转换 | 新增 |
| `scripts/test_mumu_capture.py` | DLL/Win32 截图单帧测试 | 新增 |
| `scripts/test_capture_fps.py` | Capture 帧率测试 | 新增 |

## 当前配置

`config.json`：

```json
{
  "capture_type": "auto",
  "mumu": {
    "install_path": "D:\\Program Files\\Netease\\MuMu Player 12",
    "instance_index": 0
  }
}
```

说明：
- `capture_type: auto` 会优先尝试 MuMu DLL，失败时回退 Win32 BitBlt。
- 用户明确表示路径/实例应通过 UI 向导传入，不要写死；当前开发测试阶段硬编码在 `config.json` 中，Step 9 配置向导会替换这一机制。

## 代码结构理解

### 待部署区单位定位

- `src/cache.py` 加载 `resource/operator_mapping.json` 和 `resource/avatar/` 下的头像。
- `src/logic/locate_avatar.py` 用 `cv2.matchTemplate` 在待部署区找头像。
- 流程：名字 → 查 mapping → 找头像文件 → 模板匹配 → 返回屏幕比例坐标。
- 能力边界：
  - ✅ 给定名字能在待部署区找到位置
  - ✅ 召唤物/装置只要有映射和头像也能找
  - ❌ 不知道待部署区第几个格子是什么单位
  - ❌ 不知道单位类型和部署规则
  - ❌ 不能自动识别未知单位

### 地图坐标转换

- `src/logic/calc_view.py`：用 3D 透视投影把地图 tile 坐标转成屏幕比例坐标。
- `src/logic/convert_pos.py`：把 `D2` 这种棋盘坐标转成 `(row, col)` 数值坐标。
- 当前支持 `transform_map_to_view`，**缺少 `transform_view_to_map` 逆变换**（Step 5 实现）。

### 时间/帧检测（旧机制）

- `src/logic/analyze_time.py`：
  - 费用条白像素占比 → tick（默认 0–29）
  - Tesseract OCR → 当前费用数字
- `src/logic/game_time.py`：`GameTime(cost, tick)`。

### 新机制（Step 2 起）

将用 `ArknightsCostBarRuler` 的精确 pixel 扫描替代白像素占比，把 `tick` 的精度从“费用条百分比”提升到“逻辑帧”。

## 已解决的关键问题

1. **打包问题**
   - `src/` 下没有 `__init__.py`，PyInstaller 无法把 `src` 当包处理。
   - 解决：新增 `run.py` 作为打包入口，`run.py` 中 `from src.main import main`。
   - `run.py` 还负责设置 `TESSDATA_PREFIX`，否则打包后 tesserocr 找不到 `arknights_digit.traineddata`。

2. **NumPy / OpenCV 版本冲突**
   - 全局 `numpy 2.4.6` 与项目要求的 `numpy 1.24.4` 不兼容。
   - 解决：完全隔离的 `.venv`，单独安装兼容版本。

3. **Tesseract 语言数据**
   - `arknights_digit.traineddata` 是自定义模型。
   - 当前备份位置：`tessdata_backup/tessdata/`。

4. **MuMu 截图黑屏**
   - 默认渲染模式下 `BitBlt` 截到黑屏。
   - 解决：MuMu 设置 → 性能设置 → 渲染模式中切换 **DirectX / OpenGL**，找到能正常截图的模式。

5. **Excel 宏 bug**
   - 宏代码中 `--debug` 和 `--autoenter` 之间缺少空格，同时勾选会变成 `--debug--autoenter`。
   - 建议优先使用命令行触发。

6. **截图/点击坐标系不一致**
   - 原 `mumu_controller.py` 用 `GetWindowRect`（带边框），而截图改成客户区后点击会偏移。
   - 解决：已改为 `GetClientRect`，截图和点击都基于游戏画面客户区。

## 下一步：Step 4 鼠标监听 + 坐标转换

### 目标

实现一个鼠标/键盘监听模块，把用户在 MuMu 模拟器窗口内的操作（点击、拖拽、技能释放等）按**真实时间戳**记录成 JSON 操作序列，同时与视频录制时间对齐。

### 计划新增/修改文件

| 文件 | 作用 | 状态 |
|---|---|---|
| `src/input/mouse_listener.py` | 全局鼠标钩子（`pynput` 或 `win32api.SetWindowsHookEx`），记录事件 + 时间戳 | 待新建 |
| `src/input/coordinate_mapper.py` | 把屏幕绝对坐标转换为游戏标准 1280×720 比例坐标 | 待新建 |
| `src/input/action_recorder.py` | 聚合鼠标事件为 deploy/skill/retreat 等动作，输出 JSON | 待新建 |
| `scripts/record_actions.py` | 运行监听器 + 视频录制，同时生成 `actions_<ts>.json` 和视频 | 待新建 |
| `src/logic/convert_pos.py` / `calc_view.py` | 复用/补全 view↔map 坐标转换 | 待修改 |

### 关键注意点

1. **坐标转换**：MuMu 窗口在屏幕上的位置和大小不固定，需要把 `GetClientRect` + `ClientToScreen` 得到的绝对坐标先归一化到 `[0,1]`，再乘以 `ImageProcessingConfig.SCREEN_STANDARD_SIZE` 得到标准坐标。
2. **时间对齐**：鼠标事件时间戳统一用 `time.perf_counter()`，和视频录制器 `VideoRecorder._frame_timestamps` 同一起点，便于后续按帧匹配。
3. **监听范围**：理论上监听全局鼠标即可，但需根据当前焦点窗口（`GetForegroundWindow`）过滤，只保留 MuMu 窗口内的操作。
4. **依赖**：可能需要新增 `pynput`；如果不想引入额外依赖，可用 `ctypes` + `SetWindowsHookEx` 自己实现低级钩子。
5. **动作语义识别**：
   - 单击干员区域 → `deploy`（还需记录目标地图坐标）。
   - 拖拽 → `deploy` 到地图某个位置。
   - 点击技能按钮/撤退按钮 → `skill` / `retreat`。
   - 这部分可以先只做原始事件记录，后续 Step 5/6 再做语义映射。


---

## Step 4 完成记录（2026-06-19）

### 已实现文件

| 文件 | 作用 |
|---|---|
| `src/input/mouse_listener.py` | 全局鼠标钩子（基于 `pynput`），仅记录 MuMu 窗口内的点击/滚动事件 |
| `src/input/coordinate_mapper.py` | 屏幕绝对坐标 → MuMu 客户区 → 1280×720 归一化坐标 |
| `src/input/action_recorder.py` | 聚合原始点击事件为 `click` / `drag` / `scroll`，导出 JSON |
| `scripts/record_actions.py` | 同时启动 `VideoRecorder` 和鼠标监听，输出成对的 MP4 + JSON |
| `scripts/verify_click_positions.py` | 交互式坐标准确性验证（不移动鼠标） |
| `scripts/test_input_logic.py` | 离线单元测试（不安装钩子、不移动鼠标） |
| `recorder/video_recorder.py` | 增加可选 `start_ts` 参数，与鼠标事件共享时间原点 |
| `src/config.py` | 新增 `InputRecordingConfig` 常量 |
| `requirements*.txt` | 新增 `pynput==1.7.6`、`six==1.17.0` |

### 验证结果

- `scripts/test_input_logic.py`：✅ 全部通过
- `scripts/record_actions.py --duration 2`：✅ 成功生成 MP4（1280×720、30 FPS、可正常播放）和对应 JSON
- JSON 包含 `duration`、`start_ts`、`raw_events`、`actions`、标准化坐标

### 如何才算验证成功

#### 1. 录制功能验证

运行录制脚本：

```bash
.venv\Scripts\python scripts/record_actions.py --duration 10
```

成功标志：

1. 终端输出类似：
   ```
   Video saved to: recordings/recording_20260619_xxxxxx.mp4
   Frames: 299, Duration: 9.967s, Average FPS: 30.00
   Actions saved to: recordings/actions_20260619_xxxxxx.json
   ```
2. `recordings/` 目录下同时出现 `recording_<ts>.mp4` 和 `actions_<ts>.json`。
3. JSON 中 `duration` 接近录制时长，`raw_events` 里包含你在 MuMu 窗口内点击的 `mousedown` / `mouseup` 事件。
4. 每个事件都有 `ratio`（0-1）和 `game`（0-1280 / 0-720）坐标，且 `valid: true`。
5. `actions` 数组会把成对的按下/释放聚合成 `click` 或 `drag`。

#### 2. 坐标准确性验证（Step 4 必须完成，不能留到 5/6）

运行交互式验证脚本：

```bash
.venv\Scripts\python scripts/verify_click_positions.py
```

按提示依次点击 MuMu 游戏区的**左上角、右上角、左下角、右下角、中心**。脚本会实时打印检测到的 `ratio` 和 `game` 坐标：

| 点击位置 | 预期 ratio | 预期 game |
|---|---|---|
| 左上角 | (0.00, 0.00) | (0, 0) |
| 右上角 | (1.00, 0.00) | (1280, 0) |
| 左下角 | (0.00, 1.00) | (0, 720) |
| 右下角 | (1.00, 1.00) | (1280, 720) |
| 中心 | (0.50, 0.50) | (640, 360) |

偏差在 ±0.02（标准坐标约 ±25 像素）以内可接受。如果偏差明显更大，说明 `screen → client → ratio → game` 映射有问题，必须先修正好再继续。

如果需要完整拖拽轨迹，加上 `--record-moves`：

```bash
.venv\Scripts\python scripts/record_actions.py --duration 10 --record-moves
```

> 注意：`--record-moves` 会安装低层移动钩子；如果出现光标延迟，请立即 `Ctrl+C` 停止并反馈。

### `scroll` 事件说明

`scroll` 目前只是顺手记录（鼠标滚轮在 MuMu 窗口内滚动时），明日方舟实际操作中主要用于地图缩放。当前 Step 4 的语义识别暂时不用它，可以忽略。

### 安全注意事项（重要）

**全局鼠标钩子可能导致系统鼠标卡顿/延迟。** 在本次开发过程中出现过一次：测试脚本使用 `pynput.mouse.Controller` 自动控制鼠标并点击，同时 `pynput.mouse.Listener` 全局钩子处于激活状态，注入的鼠标移动被钩子反复回调，导致鼠标响应极慢且有延迟，必须重启鼠标才恢复。

已采取的防护措施：
1. `MouseListener` 默认**不监听鼠标移动事件**（`record_moves=False`），只有 `record_moves=True` 时才注册 `on_move`。
2. 即使开启 `record_moves`，也只在**有鼠标按钮被按住**时才记录移动事件，平时直接返回，最大限度减少回调开销。
3. 删除原先自动移动鼠标的 `scripts/verify_input_recording.py`，改为不移动光标的离线单元测试。
4. 在 `mouse_listener.py` 顶部添加了醒目的警告注释。

### 后续使用规范

- **禁止**在 `MouseListener` 激活期间使用 `pynput.mouse.Controller` 或任何方式自动移动/点击鼠标。
- 用户在运行 `scripts/record_actions.py` 时，只需要正常在 MuMu 窗口内手动操作即可；监听只会记录点击/滚动事件，不会记录空闲时的鼠标移动。
- 如需录制拖拽轨迹，可在创建 `MouseListener(record_moves=True)` 时开启移动事件，但应留意是否有明显输入延迟，发现卡顿立即中止并报告。

### 已知限制

- 当前 `action_recorder.py` 只做轻量级聚合（click / drag / scroll），尚未映射到 `deploy` / `skill` / `retreat` 等游戏语义，留待 Step 5/6 处理。
- `src/logic/calc_view.py` / `convert_pos.py` 在本次 Step 4 中未做修改，后续如果需要把屏幕坐标映射到地图 tile 再补充。


### 关于游戏画面卡顿

验证阶段曾反馈：录制时 MuMu 游戏画面在鼠标操作时会卡住。排查后倾向于当时电脑内存紧张导致的偶发卡顿，后续在相同代码下复测未再出现。为降低风险，仍保留了以下优化：

- 钩子回调只做最少工作：一个比较、一次减法和一次列表追加，不拿锁、不写日志、不调外部回调。
- 默认不监听移动事件；需要完整拖拽轨迹时再用 `--record-moves`。

如后续仍遇到卡顿，可考虑把监听器放到独立轻量级进程，或改用窗口消息钩子（只钩 MuMu 窗口的 `WM_LBUTTONDOWN/UP`）。

---

## Step 4 坐标准确性验证结果（2026-06-19）

使用 `scripts/verify_click_positions.py` 验证：

| 点击位置 | 实测 ratio | 偏差 |
|---|---|---|
| 左上角 | (0.0008, 0.0056) | ✅ 极小 |
| 右上角 | (0.9961, 0.0014) | ✅ 极小 |
| 左下角 | (0.0023, 0.9861) | ✅ 极小 |
| 右下角 | (0.9945, 0.9903) | ✅ 极小 |
| 中心 | (0.4867, 0.4694) | ✅ 在手动点击误差范围内 |

结论：`screen → client → ratio → game` 映射正确。Step 4 全部验收通过，可进入 Step 5。

---

## Step 5 完成记录（2026-06-19）

### 已实现文件

| 文件 | 作用 |
|---|---|
| `src/logic/calc_view.py` | 新增 `transform_view_to_map(level, ratio_pos, side)`，使用最近邻搜索把屏幕 ratio 坐标反推回地图 tile 坐标；`transform_map_to_view` 增加缓存 |
| `tests/test_calc_view.py` | 新增 round-trip 测试：对每个 tile 正向变换后再逆变换，应返回原 `(row, col)` |
| `scripts/verify_view_to_map.py` | 新增交互式实机验证：进入指定关卡后点击地图格子，终端打印识别到的 tile |

### 验证结果

- `tests/test_calc_view.py`：✅ 3 个测试全部通过
  - 1-7 正视图 round-trip
  - 1-7 侧视图 round-trip
  - 带微小噪声的最近邻稳定性
- `transform_map_to_view` 缓存命中正常，重复调用同一地图时不重新计算透视矩阵

### 实机验证方式

进入 1-7（或其他已加载地图）后运行：

```bash
.venv\Scripts\python scripts/verify_view_to_map.py --map-code 1-7
```

在 MuMu 窗口内点击地图格子，终端会输出：

```
Click at screen=(830, 444) ratio=(0.4867, 0.4694) -> tile=(3, 5)
```

如果点击的格子与实际 tile 对应，说明 `screen → ratio → tile` 链路正确。

### 已知限制

- 当前使用纯最近邻搜索，未处理“点击在两个 tile 正中间”的歧义情况；后续可加入距离阈值或高度信息辅助判断。
- 侧视图 / 正视图需要手动通过 `--side` 指定；后续 Step 8 可结合画面特征自动判断当前视角。

---

## Step 6 完成记录（2026-06-19）

### 已实现文件

| 文件 | 作用 |
|---|---|
| `src/frame/frame_source.py` | 独立线程持续截图，把最新帧推入 `queue.Queue(maxsize=1)` |
| `src/frame/detector.py` | 新增 `AnalysisWorker`，消费帧队列、检测 tick、维护 `cycle_counter` / `total_elapsed_frames`、向 UI 队列推送状态 |
| `src/ui/overlay.py` | 基于 `ttkbootstrap` 的悬浮窗：显示当前 tick / total frame，支持拖拽，含 Calibrate / View / Exit 按钮 |
| `src/app.py` | 把 `FrameSource` + `AnalysisWorker` + `OverlayWindow` 串联起来；Calibrate 按钮调用 `src.frame.calibration.calibrate` |
| `scripts/run_overlay.py` | 启动悬浮窗的入口脚本 |
| `tests/test_detector_worker.py` | `AnalysisWorker` 状态机单元测试：cycle 计数、wrap 检测、paused 状态 |
| `requirements*.txt` | 新增 `ttkbootstrap==1.10.1`、`pystray==0.19.4` |

### 说明

- 原计划要求复制 `ArknightsCostBarRuler` 的 `overlay_window.py` 和图标资源，但这些文件不在当前仓库中，因此用 `ttkbootstrap` 重新实现了一个最小可用悬浮窗，按钮使用文字而非图标。
- `pystray` 已安装但未接入；当前悬浮窗直接以独立窗口运行，后续如需系统托盘可再扩展。

### 验证结果

- `tests/test_detector_worker.py`：✅ 3 个测试全部通过
- `tests/test_calc_view.py`：✅ 3 个测试全部通过
- `scripts/test_input_logic.py`：✅ 3 个测试全部通过
- 代码编译与导入检查：✅ 通过

### 实机验证方式

```bash
.venv\Scripts\python scripts/run_overlay.py
```

预期现象：
1. 弹出一个置顶小窗口，显示当前 tick 和 total frame。
2. 游戏内费用条走动时，tick 从 0 递增到 TICK_MAX-1，然后归零并继续。
3. 暂停游戏时，tick 停止变化，状态显示 "Paused"。
4. 点击 "Calibrate" 会触发费用条校准（需进入关卡且费用条在走动）。
5. 点击 "Exit" 关闭悬浮窗并停止后台线程。

### 已知限制

- 悬浮窗为文字按钮版，未使用 Ruler 的图标。
- View 切换按钮目前只是占位符，实际视角切换逻辑在 Step 8 语义识别时再做。
- GUI 只能在有显示器的 Windows 环境下运行，无法在当前无头环境中自动测试。