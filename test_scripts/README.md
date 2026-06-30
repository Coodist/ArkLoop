# test_scripts / 开发调试脚本

这个目录存放项目开发、调试、验证用的独立脚本，**不属于正式运行流程**。正式入口仍然是 `scripts/arkloop_webview.py` 和 `run.py`。

## 怎么运行

所有脚本都应该**在项目根目录**执行，这样 `sys.path` 才能正确找到 `src/` 和 `recorder/`：

```powershell
cd C:\Users\assert\Downloads\prts-plus-test
.venv\Scripts\python test_scripts\xxx.py [参数]
```

> 如果你用 Bash：`.venv/Scripts/python test_scripts/xxx.py`

---

## 目录

### 1. 实时监控 / 录制调试

| 脚本 | 用途 |
|---|---|
| `action_monitor.py` | 在新后端上复现 `test_action_state_machine.py` 的实时打印监控行为，用于回归测试。 |
| `analyze_recording.py` | 离线扫描录制视频，做费用条/语义动作标注分析。 |
| `record_test.py` | 测试视频录制功能，录制 N 秒游戏窗口并保存到 `recordings/`。 |
| `run_overlay.py` | 运行状态浮窗/覆盖层。 |

### 2. 识别 / 校准验证

| 脚本 | 用途 |
|---|---|
| `debug_recognition.py` | 调试录制动作为什么没被识别成部署/技能/撤退，打印识别分数和忽略原因。 |
| `show_action_regions.py` | 显示动作识别使用的区域。 |
| `show_cost_area.py` | 显示费用条区域。 |
| `show_slot_layout.py` | 可视化 MAA 检测到的干员槽位布局。 |
| `test_calibration_logic.py` | 费用条校准/检测逻辑的离线单元测试，**不需要游戏或模拟器**。 |
| `verify_calibration.py` | 实时验证费用条校准，持续打印检测到的 tick。 |
| `verify_step7.py` | Step 7 端到端验证离线费用条扫描管道。 |

### 3. 坐标 / UI 区域验证

| 脚本 | 用途 |
|---|---|
| `verify_click_positions.py` | 验证点击坐标映射到 MuMu 窗口是否正确。 |
| `verify_view_to_map.py` | 验证 `transform_view_to_map`，打印点击位置对应的地图 tile。 |
| `visualize_recorded_regions.py` | 在截图上叠加动作识别使用的区域。 |
| `visualize_regions.py` | 捕获一帧并叠加识别区域。 |
| `visualize_ui_regions.py` | 捕获游戏窗口并叠加 UI 检测区域（撤退/技能/部署区）。 |

### 4. 鼠标 / 输入调试

| 脚本 | 用途 |
|---|---|
| `debug_mouse_events.py` | 打印 pynput 全局鼠标事件，检查事件是否真实送达。 |
| `debug_fallback_click.py` | 调试 fallback 点击逻辑。 |
| `mouse_debug.py` | 独立鼠标事件调试，打印原始坐标、前景窗口、映射后的 MuMu 比例。 |
| `test_input_logic.py` | 输入记录模块的离线单元测试。 |
| `test_mumu_capture.py` | 测试 MuMu 截图并保存 patch。 |
| `verify_avatar_patch_capture.py` | 验证头像 patch 捕获事件。 |

### 5. 头像匹配 / 遮挡测试

| 脚本 | 用途 |
|---|---|
| `crop_avatar_test.py` | 测试头像裁剪/匹配流程。 |
| `test_avatar_cursor_occlusion.py` | 合成测试：鼠标光标遮挡对头像模板匹配的影响。 |
| `test_avatar_cursor_occlusion2.py` | 带亮度/压缩噪声的合成遮挡测试。 |

### 6. 其他单元 / 离线测试

| 脚本 | 用途 |
|---|---|
| `test_action_state_machine.py` | 实时状态机测试，捕获鼠标动作并交给 `ActionWorker` 异步处理。 |
| `test_capture_fps.py` | 测量 30 秒内实际截图 FPS。 |
| `test_recorder_logic.py` | 录制逻辑离线测试。 |
| `ocr_roi_tester.py` | 交互式 ROI + OCR 测试，框选区域后打印 OCR 结果。 |
| `calibrate_ui_buttons.py` | 校准 UI 按钮位置。 |

### 7. UI 原型

| 脚本 | 用途 |
|---|---|
| `arkloop_ui_prototype.py` | 基于 Figma SVG 的 Tkinter Canvas 早期 UI 原型。 |
| `axis_editor_ui_prototype.py` | 双面板时间轴编辑器原型。 |

---

## 常用命令示例

```powershell
# 实时验证费用条校准
.venv\Scripts\python test_scripts\verify_calibration.py

# 调试为什么录制动作没被识别
.venv\Scripts\python test_scripts\debug_recognition.py --map-code 1-7

# 验证点击坐标映射
.venv\Scripts\python test_scripts\verify_click_positions.py

# 可视化动作识别区域
.venv\Scripts\python test_scripts\visualize_regions.py --map 1-7 --view side

# 测试视频录制 10 秒
.venv\Scripts\python test_scripts\record_test.py --duration 10

# 离线校准逻辑单元测试
.venv\Scripts\python test_scripts\test_calibration_logic.py
```

---

## 注意事项

1. 这些脚本大多需要 `.venv` 已安装依赖、MuMu 模拟器窗口可被发现。
2. 部分脚本会往 `recordings/`、`debug/` 或根目录写临时图片/JSON；这些目录已在 `.gitignore` 中排除。
3. 脚本里原有的 `sys.path.insert` 路径计算基于文件所在目录的父目录，所以从 `scripts/` 移到 `test_scripts/` 后仍能正确指向项目根目录，**不需要修改源码**。
