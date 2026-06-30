# tools / 资源与构建工具

这个目录存放**资源同步、资源预处理、构建辅助**类的脚本。它们不是运行时代码，但在更新游戏资源或准备发布时会用到。

---

## 文件说明

| 脚本 | 用途 | 是否需要联网 |
|---|---|---|
| `sync_new_resource.py` | 从上游 GitHub 仓库拉取最新游戏资源（头像、地图、数据表），输出到 `new_resource/` | ✅ 是（除非用 `--skip-git`） |
| `process_battle_data.py` | 从 `resource/battle_data.json` 生成 `resource/operator_mapping.json`（干员名 → ID 映射） | ❌ 否 |
| `process_overview.py` | 从 `resource/map/overview.json` 生成 `resource/level_code_mapping.json` 和 `resource/level_name_mapping.json` | ❌ 否 |

---

## 完整更新资源流程

### 1. 拉取上游最新资源

```powershell
cd C:\Users\assert\Downloads\prts-plus-test
.venv\Scripts\python tools\sync_new_resource.py
```

这会从以下仓库拉取文件并放到 `new_resource/`，结构与 `resource/` 一致：

- `avatar/` ← `yuanyan3060/ArknightsGameResource@main`
- `map/` ← `MaaAssistantArknights/MaaAssistantArknights@dev-v2`
- `battle_data.json` / `character_table.json` / `range_table.json` 等

拉取完成后，`sync_new_resource.py` 还会自动生成 `new_resource/*_mapping.json` 和 `new_resource/unit_metadata.json`。

### 2. 把 `new_resource/` 同步到 `resource/`

`sync_new_resource.py` 只写到 `new_resource/`，不会直接覆盖 `resource/`。你需要手动确认后再替换或合并：

```powershell
# 比较差异
xcopy /E /I /D new_resource resource

# 或者用 robocopy 镜像（会覆盖，谨慎）
robocopy new_resource resource /MIR
```

> 也可以直接让脚本输出到 `resource/`，但不推荐，因为会覆盖你本地可能修改过的文件。

### 3. 重新生成映射表

如果你只更新了 `resource/battle_data.json` 或 `resource/map/overview.json`，可以单独跑：

```powershell
.venv\Scripts\python tools\process_battle_data.py
.venv\Scripts\python tools\process_overview.py
```

这两个脚本会基于项目根目录的 `resource/` 重新生成：

- `resource/operator_mapping.json`
- `resource/level_code_mapping.json`
- `resource/level_name_mapping.json`

---

## 常用命令速查

```powershell
# 联网拉取最新资源
.venv\Scripts\python tools\sync_new_resource.py

# 只基于本地 new_resource/ 生成 mapping，跳过 git 拉取
.venv\Scripts\python tools\sync_new_resource.py --skip-git

# 查看 sync 脚本的所有参数
.venv\Scripts\python tools\sync_new_resource.py --help

# 单独生成 operator_mapping.json
.venv\Scripts\python tools\process_battle_data.py

# 单独生成 level_code_mapping.json / level_name_mapping.json
.venv\Scripts\python tools\process_overview.py
```

---

## 注意事项

1. **运行目录**：这些脚本基于 `Path(__file__).parent.parent` 定位项目根目录，所以**不一定要从项目根目录执行**，但从根目录执行最稳妥。
2. **网络依赖**：`sync_new_resource.py` 默认会 `git clone` 上游仓库，需要能访问 GitHub。
3. **临时目录**：同步过程中会创建 `_tmp_sync/` 目录，脚本结束后会清理。
4. **映射表生成**：`process_battle_data.py` 还会生成一份去掉中文弯引号（`“”`）的干员名映射，避免搜索时因为引号搜不到。
