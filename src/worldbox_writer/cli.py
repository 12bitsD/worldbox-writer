"""
WorldBox Writer — 命令行 Demo 入口

用法：
  # 使用沙盒内置 LLM（无需配置）
  python -m worldbox_writer.cli

  # 使用 Kimi
  LLM_PROVIDER=kimi LLM_API_KEY=sk-xxx python -m worldbox_writer.cli

  # 自定义前提和步数
  python -m worldbox_writer.cli --premise "一个赛博朋克世界里的侦探" --ticks 6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.graph import run_simulation
from worldbox_writer.utils.llm import get_provider_info

# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
MAGENTA = "\033[35m"


def _c(text: str, *codes: str) -> str:
    return "".join(codes) + text + RESET


def _divider(char: str = "─", width: int = 60) -> str:
    return _c(char * width, DIM)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def print_banner() -> None:
    banner = r"""
 __        __         _     _ ____
 \ \      / /__  _ __| | __| | __ )  _____  __
  \ \ /\ / / _ \| '__| |/ _` |  _ \ / _ \ \/ /
   \ V  V / (_) | |  | | (_| | |_) | (_) >  <
    \_/\_/ \___/|_|  |_|\__,_|____/ \___/_/\_\
                W R I T E R
    """
    print(_c(banner, BOLD, CYAN))
    print(_c("  Agent 集群驱动的沙盒小说创作系统", DIM))
    print()


def print_world_state(world: WorldState) -> None:
    print(_divider())
    print(_c("  世界状态", BOLD, YELLOW))
    print(_divider())
    print(f"  标题：{world.title}")
    print(f"  前提：{world.premise}")
    print(
        f"  角色（{len(world.characters)}）："
        + "、".join([c.name for c in list(world.characters.values())[:5]])
    )
    if world.factions:
        print(
            f"  势力（{len(world.factions)}）："
            + "、".join([f.get("name", "") for f in world.factions[:4]])
        )
    if world.locations:
        print(
            f"  地点（{len(world.locations)}）："
            + "、".join([loc.get("name", "") for loc in world.locations[:4]])
        )
    print(
        f"  约束（{len(world.constraints)}）："
        + "、".join([c.name for c in world.constraints[:4]])
    )
    print(_divider())
    print()


def print_node(node, tick: int) -> None:
    type_colors = {
        "setup": CYAN,
        "conflict": RED,
        "development": RESET,
        "climax": MAGENTA,
        "resolution": GREEN,
        "branch": YELLOW,
    }
    color = type_colors.get(node.node_type.value, RESET)
    print()
    print(
        _c(f"  ◆ 第{tick}幕 [{node.node_type.value.upper()}] {node.title}", BOLD, color)
    )
    print(_c(f"  {node.description}", DIM))
    if node.rendered_text:
        print()
        for line in node.rendered_text.split("\n"):
            if line.strip():
                print(f"  {line}")
    print()


def intervention_prompt(context: str) -> str:
    print()
    print(_divider("═"))
    print(_c("  ⚡ 关键节点 — 需要你的干预", BOLD, YELLOW))
    print(_divider("═"))
    print(f"\n  {context}\n")
    print("  你可以：")
    print("  [1] 什么都不做，让故事自然发展")
    print("  [2] 输入你的干预指令（自然语言）")
    print()

    choice = input(_c("  你的选择 > ", BOLD)).strip()

    if choice == "1" or not choice:
        return "继续按照当前走向发展"
    elif choice == "2":
        instruction = input(_c("  输入干预指令 > ", BOLD)).strip()
        return instruction if instruction else "继续按照当前走向发展"
    else:
        # 直接把输入当作指令
        return choice


def export_results(world: WorldState, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 导出小说正文
    novel_path = output_dir / "novel.txt"
    with open(novel_path, "w", encoding="utf-8") as f:
        f.write(f"{world.title}\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"前提：{world.premise}\n\n")
        f.write("=" * 40 + "\n\n")
        for node in world.nodes.values():
            if node.rendered_text:
                f.write(f"【{node.title}】\n\n")
                f.write(node.rendered_text)
                f.write("\n\n" + "-" * 40 + "\n\n")

    # 导出世界设定
    settings_path = output_dir / "world_settings.json"
    settings = {
        "title": world.title,
        "premise": world.premise,
        "world_rules": world.world_rules,
        "factions": world.factions,
        "locations": world.locations,
        "characters": [
            {
                "name": c.name,
                "personality": c.personality,
                "goals": c.goals,
                "status": c.status.value,
                "memory_count": len(c.memory),
            }
            for c in world.characters.values()
        ],
        "constraints": [
            {
                "name": c.name,
                "rule": c.rule,
                "severity": c.severity.value,
                "type": c.constraint_type.value,
            }
            for c in world.constraints
        ],
    }
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    # 导出故事时间线
    timeline_path = output_dir / "timeline.md"
    with open(timeline_path, "w", encoding="utf-8") as f:
        f.write(f"# {world.title} — 故事时间线\n\n")
        for i, node in enumerate(world.nodes.values(), 1):
            f.write(f"## 第{i}幕：{node.title} `[{node.node_type.value}]`\n\n")
            f.write(f"{node.description}\n\n")
            if node.intervention_instruction:
                f.write(f"> 用户干预：{node.intervention_instruction}\n\n")

    print(_c(f"\n  ✓ 小说正文  → {novel_path}", GREEN))
    print(_c(f"  ✓ 世界设定  → {settings_path}", GREEN))
    print(_c(f"  ✓ 故事时间线 → {timeline_path}", GREEN))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WorldBox Writer — Agent 集群驱动的沙盒小说创作系统"
    )
    parser.add_argument(
        "--premise",
        type=str,
        default="",
        help="故事前提（一句话）",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=6,
        help="最大推演步数（默认 6）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./output",
        help="输出目录（默认 ./output）",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="禁用交互式干预（自动跳过所有干预节点）",
    )
    args = parser.parse_args()

    print_banner()

    # 显示 LLM 配置
    info = get_provider_info()
    print(
        _c(f"  LLM Provider: {info['provider']}  |  Model: {info['model_sample']}", DIM)
    )
    print()

    # 获取故事前提
    premise = args.premise
    if not premise:
        print(_c("  请输入你的故事前提（一句话描述你想要的世界和故事）：", BOLD))
        print(
            _c(
                "  例如：一个修仙和赛博朋克混合的废土世界，主角是个被门派抛弃的天才",
                DIM,
            )
        )
        print()
        premise = input(_c("  > ", BOLD, CYAN)).strip()
        if not premise:
            premise = "一个古代江湖世界，一个被门派驱逐的侠客踏上复仇之路"
            print(_c(f"  使用默认前提：{premise}", DIM))

    print()
    print(_c(f"  开始推演：{premise}", BOLD))
    print(_c(f"  最大步数：{args.ticks}", DIM))
    print()

    rendered_nodes = []

    def on_node_rendered(node, world):
        rendered_nodes.append(node)
        print_node(node, world.tick)

    def intervention_cb(context: str) -> str:
        if args.no_interactive:
            return "继续按照当前走向发展"
        return intervention_prompt(context)

    try:
        print(_c("  正在初始化世界...", DIM))
        final_world = run_simulation(
            premise=premise,
            max_ticks=args.ticks,
            intervention_callback=intervention_cb,
            on_node_rendered=on_node_rendered,
        )
    except KeyboardInterrupt:
        print(_c("\n\n  推演已中断", YELLOW))
        sys.exit(0)
    except Exception as e:
        print(_c(f"\n  推演出错：{e}", RED))
        raise

    # 显示最终世界状态
    print_world_state(final_world)

    # 导出结果
    print(_c("  正在导出结果...", DIM))
    export_results(final_world, Path(args.output))

    print()
    print(_c("  故事推演完成！", BOLD, GREEN))
    print()


if __name__ == "__main__":
    main()
