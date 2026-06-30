# prts-plus 项目交接文档

> 生成时间：2026-06-19  
> 项目位置：`C:\Users\assert\Downloads\prts-plus-main`

---

## 一、当前可运行状态

- `prts+.exe` + `_internal/` 已部署在项目根目录，可直接命令行运行。
- Excel 宏启动也已验证可运行（需 Microsoft Excel + 兼容渲染模式的 MuMu）。
- 命令行运行示例：

```powershell
cd C:\Users\assert\Downloads\prts-plus-main
.\prts+.exe --xlsm "C:\Users\assert\Downloads\prts-plus-main\sample 1-7.xlsm" --autoenter
```

参数说明：
- `--xlsm`：Excel 文件路径，**建议使用绝对路径**
- `--autoenter`：自动进入关卡
- `--debug`：输出详细日志

---

## 二、依赖环境

- Python 3.11.6
- 虚拟环境：`.venv/`（隔离环境）
- `tesserocr` 是从全局 `site-packages` 拷贝进 `.venv` 的，因为它需要从源码编译且依赖 Tesseract 开发库
- 重新打包命令：

```bash
cd C:\Users\assert\Downloads\prts-plus-main
source .venv/Scripts/activate
pyinstaller -y --name "prts+" --onedir --add-data "resource;resource" --add-data "hook;hook" run.py
# 打包结果在 dist/prts+/ 下，需复制到根目录
cp -r dist/prts+/* .
```

---

## 三、已解决的关键问题

### 1. 打包问题

- `src/` 下没有 `__init__.py`，PyInstaller 无法把 `src` 当包处理。
- 解决方案：新增 `run.py` 作为打包入口，`run.py` 中 `from src.main import main`。
- `run.py` 还负责设置 `TESSDATA_PREFIX` 环境变量，否则打包后 tesserocr 找不到 `arknights_digit.traineddata`。

### 2. NumPy / OpenCV 版本冲突

- 全局 `numpy 2.4.6` 与项目要求的 `numpy 1.24.4` 不兼容。
- 解决方案：创建完全隔离的 `.venv`，单独安装 `numpy==1.24.4` 和 `opencv-python==4.9.0.80`，再拷贝全局 `tesserocr`。

### 3. Tesseract 语言数据

- `arknights_digit.traineddata` 是项目自定义的 OCR 模型，官方 Tesseract 没有。
- 来源：从 release 包 `_internal/Tesseract-OCR/tessdata/` 中复制。
- 当前存放位置：`C:\Users\assert\Downloads\prts-plus-main\tessdata_backup/tessdata/`

### 4. MuMu 截图黑屏

- 默认渲染模式下 `BitBlt` 截到黑屏。
- 解决方案：在 MuMu 设置 → 性能设置 → 渲染模式中切换 **DirectX / OpenGL**，找到能正常截图的模式。

### 5. Excel 宏 bug

- 宏代码中 `--debug` 和 `--autoenter` 之间缺少空格：
  ```vba
  command = """" & scriptPath & """ --xlsm """ & excelPath & """ " & debugFlag & enterFlag
  ```
- 同时勾选两个选项时命令会变成 `--debug--autoenter`，导致参数解析异常。
- 建议优先使用命令行触发。

---

## 四、代码结构理解

### 待部署区单位定位机制

- `src/logic/locate_avatar.py`：模板匹配定位头像位置
- `src/cache.py`：加载 `resource/operator_mapping.json` 和 `resource/avatar/` 下的头像
- 流程：名字 → 查 mapping → 找头像文件 → 在待部署区做 `cv2.matchTemplate` → 返回屏幕比例坐标

### 能力边界

- ✅ 给定名字能在待部署区找到位置
- ✅ 召唤物/装置只要有映射和头像也能找
- ❌ 不知道待部署区第几个格子是什么单位
- ❌ 不知道单位类型（干员/召唤物/装置）和部署规则
- ❌ 不能自动识别未知单位

### 地图坐标转换

- `src/logic/calc_view.py`：用 3D 透视投影把地图 tile 坐标转成屏幕比例坐标
- `src/logic/convert_pos.py`：把 `D2` 这种棋盘坐标转成 `(row, col)` 数值坐标
- 当前支持 `transform_map_to_view`，**缺少 `transform_view_to_map` 逆变换**

### 时间/帧检测

- `src/logic/analyze_time.py`：通过费用条白像素占比计算 tick，通过 Tesseract OCR 识别费用数字
- `src/logic/game_time.py`：`GameTime(cost, tick)`，tick 周期默认 30

---

## 五、下一步目标

参见 `C:\Users\assert\Downloads\abundant-launching-dragon.md`。

核心方向：
1. 将 prts-plus 执行端从 Excel 触发重构为 JSON 轴 + 命令行/UI 触发（Step 0）
2. 集成 ArknightsCostBarRuler 的精确帧检测和悬浮窗 UI
3. 实现录制 → 离线分析 → 生成轴的完整流程

---

## 六、风险提醒

- 必须安装 **Microsoft Excel（Office）**，WPS 不兼容 `win32com` 的 `Excel.Application`
- 必须保证 MuMu 渲染模式与 `BitBlt` 截图兼容
- 录制功能中的部署识别仍是 TODO，需要先做原型验证
- 单位详情界面检测方法（撤退/技能完成帧判定）仍是 TODO
