#!/usr/bin/env python3
"""
sync_new_resource.py

从上游 GitHub 仓库拉取游戏资源，输出到 new_resource/ 目录。
目录结构与 resource/ 完全一致。

来源：
  new_resource/avatar/            ← yuanyan3060/ArknightsGameResource@main  avatar/*
  new_resource/map/               ← MaaAssistantArknights/MaaAssistantArknights@dev-v2  resource/Arknights-Tile-Pos/*
  new_resource/battle_data.json   ← 同上  resource/battle_data.json
  new_resource/character_table.json  ← Kengxxiao/ArknightsGameData@master  zh_CN/gamedata/excel/character_table.json
  new_resource/range_table.json      ← 同上  zh_CN/gamedata/excel/range_table.json
  new_resource/*_mapping.json     ← 由本脚本处理生成
  new_resource/unit_metadata.json ← 由本脚本处理生成
"""

import argparse
import os
import stat
import sys
import subprocess
import shutil
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent  # project root (tools/..)
TMP = ROOT / "_tmp_sync"
OUT = ROOT / "new_resource"

MIN_GIT = (2, 25)

REPOS = [
    {
        "name": "ark-resource",
        "url": "https://github.com/yuanyan3060/ArknightsGameResource.git",
        "branch": "main",
        "patterns": ["avatar/*"],
        "copy": [
            ("avatar", OUT / "avatar"),
        ],
    },
    {
        "name": "maa",
        "url": "https://github.com/MaaAssistantArknights/MaaAssistantArknights.git",
        "branch": "dev-v2",
        "patterns": [
            "resource/Arknights-Tile-Pos/*",
            "resource/battle_data.json",
        ],
        "copy": [
            ("resource/Arknights-Tile-Pos", OUT / "map"),
            ("resource/battle_data.json", OUT / "battle_data.json"),
        ],
    },
    {
        "name": "arknights-game-data",
        "url": "https://github.com/Kengxxiao/ArknightsGameData.git",
        "branch": "master",
        "patterns": [
            "zh_CN/gamedata/excel/character_table.json",
            "zh_CN/gamedata/excel/range_table.json",
        ],
        "copy": [
            ("zh_CN/gamedata/excel/character_table.json", OUT / "character_table.json"),
            ("zh_CN/gamedata/excel/range_table.json", OUT / "range_table.json"),
        ],
    },
]


def check_git():
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=True
        )
        # 解析 "git version 2.39.1.windows.1" 或 "git version 2.43.0"
        token = result.stdout.split()[2]
        parts = token.split(".")
        major, minor = int(parts[0]), int(parts[1])
    except FileNotFoundError:
        print("错误：未找到 git，请安装后重试。")
        print("下载地址：https://git-scm.com/downloads")
        sys.exit(1)
    except (IndexError, ValueError):
        print(f"警告：无法解析 git 版本号（{result.stdout.strip()}），跳过版本检查。")
        return

    if (major, minor) < MIN_GIT:
        print(f"错误：当前 git 版本 {major}.{minor} 过低，需要 >= {MIN_GIT[0]}.{MIN_GIT[1]}")
        print("请更新 git：https://git-scm.com/downloads")
        sys.exit(1)

    print(f"  git {major}.{minor}（完整版本号：{token}）OK")


def rmtree_force(path):
    """Windows 上 .git 目录含只读文件，需先解除只读属性再删除。"""
    def handle_error(func, fpath, exc):
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)

    # Python 3.12+ 用 onexc，旧版用 onerror
    try:
        shutil.rmtree(path, onexc=handle_error)
    except TypeError:
        shutil.rmtree(path, onerror=handle_error)


def run(cmd, cwd=None):
    print(f"    $ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def sparse_fetch(name, url, branch, patterns):
    """
    使用 partial clone + sparse checkout 只下载指定路径的文件。

    --filter=blob:none : clone 时不下载任何文件内容（blob），只拿 tree/commit
    --no-checkout      : clone 后不自动检出工作区
    core.sparseCheckout: 启用 sparse checkout，仅检出匹配 patterns 的路径
    git reset --hard   : 按 sparse patterns 检出工作区，按需拉取对应 blob
    """
    repo_dir = TMP / name
    if repo_dir.exists():
        rmtree_force(repo_dir)

    run([
        "git", "clone",
        "--depth", "1",
        "--filter", "blob:none",
        "--no-checkout",
        "--branch", branch,
        url, str(repo_dir),
    ])

    run(["git", "config", "core.sparseCheckout", "true"], cwd=repo_dir)
    (repo_dir / ".git" / "info" / "sparse-checkout").write_text(
        "\n".join(patterns) + "\n", encoding="utf-8"
    )

    run(["git", "reset", "--hard", f"origin/{branch}"], cwd=repo_dir)

    return repo_dir


def copy_resource(repo_dir, copy_rules):
    for src_rel, dst in copy_rules:
        src = repo_dir / src_rel
        if not src.exists():
            print(f"    警告：源路径不存在，跳过 {src_rel}")
            continue
        if dst.exists():
            if dst.is_dir():
                rmtree_force(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
            count = sum(1 for p in dst.rglob("*") if p.is_file())
            print(f"    {src_rel} → {dst.relative_to(ROOT)}  ({count} 个文件)")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            size_kb = dst.stat().st_size // 1024
            print(f"    {src_rel} → {dst.relative_to(ROOT)}  ({size_kb} KB)")


def _resolve_new_or_resource(path_in_out: Path) -> Path | None:
    """优先使用 new_resource/ 中的文件，不存在则回退到 resource/。"""
    if path_in_out.exists():
        return path_in_out
    rel = path_in_out.relative_to(OUT)
    fallback = ROOT / "resource" / rel
    if fallback.exists():
        return fallback
    return None


def generate_mappings():
    # 对应 tools/process_overview.py
    overview_path = _resolve_new_or_resource(OUT / "map" / "overview.json")
    if overview_path:
        overview = json.loads(overview_path.read_text(encoding="utf-8"))
        (OUT / "level_code_mapping.json").write_text(
            json.dumps(
                {v["code"]: v["filename"] for v in overview.values()},
                ensure_ascii=False, indent=4,
            ),
            encoding="utf-8",
        )
        (OUT / "level_name_mapping.json").write_text(
            json.dumps(
                {v["name"]: v["filename"] for v in overview.values()},
                ensure_ascii=False, indent=4,
            ),
            encoding="utf-8",
        )
        print("    生成：level_code_mapping.json, level_name_mapping.json")
    else:
        print("    警告：map/overview.json 不存在，跳过 level mapping 生成")

    # 对应 tools/process_battle_data.py
    battle_path = _resolve_new_or_resource(OUT / "battle_data.json")
    operator_mapping_path = OUT / "operator_mapping.json"
    if battle_path:
        battle = json.loads(battle_path.read_text(encoding="utf-8"))
        name_map = {}
        for key, val in battle["chars"].items():
            name = val["name"]
            name_map[name] = key
            # 同时保存一份去掉弯引号的版本（与原脚本行为一致）
            quoteless = name.replace("“", "").replace("”", "")
            if quoteless != name:
                name_map[quoteless] = key
        operator_mapping_path.write_text(
            json.dumps(name_map, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        print("    生成：operator_mapping.json")
    else:
        print("    警告：battle_data.json 不存在，跳过 operator_mapping 生成")

    # 生成 unit_metadata.json
    character_path = _resolve_new_or_resource(OUT / "character_table.json")
    range_path = _resolve_new_or_resource(OUT / "range_table.json")
    if character_path and operator_mapping_path.exists():
        generate_unit_metadata(
            character_path=character_path,
            range_path=range_path,
            operator_mapping_path=operator_mapping_path,
            output_path=OUT / "unit_metadata.json",
        )
    else:
        print("    警告：character_table.json 或 operator_mapping.json 不存在，跳过 unit_metadata 生成")


def _profession_display(profession: str) -> str:
    mapping = {
        "WARRIOR": "近卫",
        "TANK": "重装",
        "PIONEER": "先锋",
        "SPECIAL": "特种",
        "SNIPER": "狙击",
        "CASTER": "术师",
        "MEDIC": "医疗",
        "SUPPORT": "辅助",
        "TOKEN": "召唤物",
        "TRAP": "装置",
    }
    return mapping.get(profession, profession)


def _range_is_symmetric(grids: list) -> bool:
    """判断攻击范围是否关于列轴（即左右）对称。

    若范围中每一格 (row, col) 都存在镜像格 (row, -col)，
    则认为该范围不随朝向改变，部署时不需要选择方向。
    """
    cells = {(g["row"], g["col"]) for g in grids}
    for row, col in cells:
        if (row, -col) not in cells:
            return False
    return True


def _needs_direction(char_entry: dict, range_table: dict | None) -> bool:
    profession = char_entry.get("profession", "")
    if profession == "TRAP":
        return False

    # 普通干员（非 TOKEN/TRAP）部署时均需要选择方向
    if profession != "TOKEN":
        return True

    # TOKEN / 召唤物根据攻击范围是否左右对称判断
    phases = char_entry.get("phases") or []
    range_id = phases[0].get("rangeId") if phases else None
    if not range_id:
        return False

    if range_table is None:
        return False

    range_data = range_table.get(range_id)
    if not range_data:
        return False

    grids = range_data.get("grids", [])
    if not grids:
        return False

    return not _range_is_symmetric(grids)


def generate_unit_metadata(
    character_path: Path,
    range_path: Path | None,
    operator_mapping_path: Path,
    output_path: Path,
) -> None:
    """读取 character_table 与 range_table，生成 unit_metadata.json。"""
    print("    生成：unit_metadata.json")

    character_table = json.loads(character_path.read_text(encoding="utf-8"))
    range_table = json.loads(range_path.read_text(encoding="utf-8")) if range_path else None
    operator_mapping = json.loads(operator_mapping_path.read_text(encoding="utf-8"))

    metadata = {}
    for cn_name, char_id in operator_mapping.items():
        char_entry = character_table.get(char_id)
        if not char_entry:
            print(f"      警告：character_table 中找不到 {char_id}（{cn_name}），跳过")
            continue

        metadata[cn_name] = {
            "char_id": char_id,
            "name": cn_name,
            "profession": char_entry.get("profession", ""),
            "profession_display": _profession_display(char_entry.get("profession", "")),
            "sub_profession_id": char_entry.get("subProfessionId", ""),
            "needs_direction": _needs_direction(char_entry, range_table),
        }

    output_path = Path(output_path).resolve()
    output_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    print(f"      共 {len(metadata)} 条单位元数据 → {output_path.name}")


def main():
    parser = argparse.ArgumentParser(
        description="从上游仓库同步 prts-plus 资源到 new_resource/"
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="跳过所有 git 拉取，只基于 new_resource/ 中已存在的文件生成 mapping JSON",
    )
    args = parser.parse_args()

    bar = "=" * 52
    print(bar)
    print("  PRTS+ 资源同步脚本")
    print(bar)

    total_steps = len(REPOS) + 2  # repos + cleanup + generate mappings

    # Step 0: 版本检测
    print(f"\n[0/{total_steps}] 检查 git 版本")
    check_git()

    TMP.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)

    failed_repos: list[str] = []

    if args.skip_git:
        print("\n  参数 --skip-git：跳过 git 拉取，直接生成 mapping")
    else:
        try:
            # Step 1~N: 拉取各仓库
            for i, repo in enumerate(REPOS, 1):
                print(f"\n[{i}/{total_steps}] 拉取 {repo['name']}")
                print(f"  URL  : {repo['url']}")
                print(f"  分支 : {repo['branch']}")
                print(f"  路径 : {', '.join(repo['patterns'])}")
                try:
                    repo_dir = sparse_fetch(
                        repo["name"], repo["url"], repo["branch"], repo["patterns"]
                    )
                    copy_resource(repo_dir, repo["copy"])
                except subprocess.CalledProcessError as e:
                    failed_repos.append(repo["name"])
                    print(f"    ✗ 拉取失败：{repo['name']}")
                    print(f"      错误：{e}")
                    print("      提示：可设置代理后重试，例如")
                    print("            $env:HTTPS_PROXY='http://127.0.0.1:7890'")
                    print("      或仅生成本地 mapping：")
                    print("            .venv\\Scripts\\python tools\\sync_new_resource.py --skip-git")
                    print("      或单独生成 unit_metadata：")
                    print("            .venv\\Scripts\\python scripts\\generate_unit_metadata.py --help")
                    continue
        finally:
            # 清理临时目录
            cleanup_step = len(REPOS) + 1
            if TMP.exists():
                print(f"\n[{cleanup_step}/{total_steps}] 清理临时目录 {TMP.name}/")
                rmtree_force(TMP)
                print("    已删除")

    # 最后一步：生成 mapping JSON
    final_step = total_steps
    print(f"\n[{final_step}/{total_steps}] 生成 mapping JSON")
    generate_mappings()

    print(f"\n{bar}")
    if failed_repos:
        print(f"  部分仓库同步失败：{', '.join(failed_repos)}")
        print("  请检查网络/代理设置，或使用 --skip-git 仅生成本地 mapping。")
        sys.exit(1)
    print("  完成！资源已同步至 new_resource/")
    print(bar)


if __name__ == "__main__":
    main()
