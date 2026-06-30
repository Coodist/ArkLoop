# Handoff: Step 6 完成 — 帧同步线程 + 悬浮 Overlay UI

## 当前状态

Step 6 已验证通过：

- 实时帧捕获线程 (`FrameSource`) 与分析线程 (`AnalysisWorker`) 已连通
- 悬浮窗 UI 已正常显示，能实时显示当前费用条 tick（如 `5 /30`）和计时器
- UI 风格复用了 `ArknightsCostBarRuler` 的设计
- 右键菜单可用：Calibration / Display / Timer / Exit

## 关键文件

| 文件 | 说明 |
|------|------|
| `src/ui/overlay.py` | 悬浮窗本体。现在是**单 `ttk.Window` 根窗口**，不再使用父/子窗口。包含 `_process_ui_queue`、`set_initial_state`、右键菜单、拖拽、状态切换等。 |
| `src/app.py` | 总装配。创建 `FrameSource`、`AnalysisWorker`、`OverlayWindow`，处理标定/计时器/显示模式回调。 |
| `src/frame/detector.py` | `AnalysisWorker` 消费帧队列，检测 tick，维护 `cycle_counter` / `total_elapsed_frames`，向 UI 发送 ruler 兼容消息。 |
| `src/frame/frame_source.py` | 独立线程捕获帧并推入 `frame_queue(Queue(maxsize=1))`。 |
| `scripts/run_overlay.py` | 启动入口。 |
| `tests/test_detector_worker.py` | 针对新消息格式的单元测试。 |

## UI 消息协议

`AnalysisWorker` 发出的消息：

```python
{"type": "update",
 "display_frame": "5",
 "display_total": "/30",
 "time_str": "00:00:05",
 "lap_frames": None,
 "totalFramesInCycle": 30}

{"type": "state_change",
 "state": "running",
 "display_total": "/30",
 "active_profile": "default",
 "display_mode": "0_to_n-1"}
```

`OverlayWindow._process_ui_queue` 负责消费这些消息。

## 已修复的问题

1. **父/子窗口导致 UI 不可见** → 改为 `OverlayWindow` 自己就是根窗口
2. **`ui_queue(maxsize=1)` 阻塞/丢失初始状态** → 初始状态改为直接调用 `overlay.set_initial_state(...)`，运行时更新才走 queue
3. **图标/样式加载失败** → 使用 `resource/icons/` 下的 `deco.png`、`wait.png`、`start.png`、`timer.png`

## 如何复现 / 验证

```bash
.venv\Scripts\python scripts/run_overlay.py
```

预期：屏幕右下角出现深色悬浮窗，显示当前费用 tick 和计时器。右键可打开菜单。

## 下一步（Step 7）

按原计划推进 **Step 7：离线费用条扫描 / 语义识别**。具体需求请查看项目顶层计划文档或用户给出的后续指令。

可能与以下模块相关：

- `src/frame/calibration.py`：费用条标定数据
- `src/logic/game_time.py`：游戏内时间计算
- 新的语义识别模块（待实现）

## 注意事项

- 不要回到父/子窗口方案；单根窗口在当前环境下稳定
- 初始状态不要走 `ui_queue`，避免被 worker 更新顶掉
- `OverlayWindow` 内部仍接收 queue 更新，但依赖 `state_change` 先摆放好标签
- 标定数据在 `calibration/default_30f_1280x720.json`，1280x720 分辨率
