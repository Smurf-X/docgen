import sys
import io
import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from . import __version__
from .config import Config
from .scanner import Scanner, ProjectInfo
from .analyzer import CodeAnalyzer
from .outline import Outline, DEFAULT_CHAPTERS, OPERATOR_CHAPTERS, get_default_chapters
from .generator import Generator
from .writer import Writer
from .op_analyzer import OperatorAnalyzer


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(force_terminal=True)


@click.command()
@click.argument("project_path", type=click.Path(exists=True), default=".")
@click.option(
    "--config", "-c", "config_path", default="config.yaml", help="配置文件路径"
)
@click.option("--output", "-o", "output_path", help="输出目录")
@click.option("--version", "-v", is_flag=True, help="显示版本")
@click.option("--yes", "-y", is_flag=True, help="跳过交互确认，直接生成")
def main(
    project_path: str,
    config_path: str,
    output_path: Optional[str],
    version: bool,
    yes: bool,
):
    """DocGen - 交互式文档生成工具

    PROJECT_PATH: 项目目录路径（默认当前目录）
    """
    if version:
        console.print(f"docgen version {__version__}")
        return

    config = Config.load(config_path) if Path(config_path).exists() else Config()

    if output_path:
        config.output.path = output_path

    asyncio.run(run_generation(project_path, config, yes))


async def run_generation(project_path: str, config: Config, auto_confirm: bool):
    console.print(
        Panel.fit(
            f"[bold cyan]DocGen[/] - 文档生成工具\n版本: {__version__}",
            border_style="cyan",
        )
    )

    console.print("\n[bold]步骤 1/5: 扫描项目[/]")
    with console.status("[cyan]正在扫描项目...[/]"):
        scanner = Scanner(project_path, config.scan.exclude)
        project_info = scanner.scan()
        analyzer = CodeAnalyzer(project_path)
        op_analyzer = OperatorAnalyzer(project_path)

        project_type = "general"
        if op_analyzer.has_operators():
            op_count = op_analyzer.get_operator_count()
            total_ops = sum(op_count.values())
            if total_ops >= 10:
                project_type = "operator"

    display_project_info(project_info)

    if project_type == "operator":
        console.print("\n[cyan]检测到算子类项目，将使用算子专用文档模板[/]")
        op_count = op_analyzer.get_operator_count()
        op_summary = ", ".join([f"{k}: {v}个" for k, v in op_count.items()])
        console.print(f"[cyan]算子统计: {op_summary}[/]")

    console.print("\n[bold]步骤 2/5: 确认章节[/]")

    default_chapters = get_default_chapters(project_type)

    console.print("默认章节：")
    for i, chapter in enumerate(default_chapters, 1):
        console.print(f"  {i}. {chapter}")

    if not auto_confirm:
        console.print(
            "\n[cyan]提示：直接回车使用默认章节，或输入自定义章节（逗号分隔）[/]"
        )
        user_input = input("章节列表: ").strip()

        if user_input:
            chapters = [c.strip() for c in user_input.split(",") if c.strip()]
        else:
            chapters = default_chapters.copy()
    else:
        chapters = default_chapters.copy()

    outline = Outline.from_chapter_titles(chapters)
    console.print(f"\n[green]已选择 {len(chapters)} 个章节[/]")

    console.print("\n[bold]步骤 3/5: 生成子章节[/]")

    generator = Generator(config, scanner, analyzer)
    project_info_str = project_info.to_summary()
    op_categories = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for chapter in outline.chapters:
            if chapter.title == "算子参考":
                task = progress.add_task(f"扫描算子...", total=None)
                op_categories = op_analyzer.scan_operators()
                total_ops = sum(len(cat.operators) for cat in op_categories)
                progress.update(
                    task,
                    description=f"✓ 算子参考: {len(op_categories)} 类, {total_ops} 个算子",
                )
                continue

            task = progress.add_task(f"生成 {chapter.title} 的子章节...", total=None)

            try:
                subsections = await generator.generate_subsections_for_chapter(
                    chapter, project_info_str
                )
                chapter.subsections = subsections
                progress.update(
                    task, description=f"✓ {chapter.title}: {len(subsections)} 个子章节"
                )
            except Exception as e:
                console.print(f"[red]✗ {chapter.title}: {e}[/]")
                progress.update(task, description=f"✗ {chapter.title}: 生成失败")

    console.print("\n[cyan]生成的子章节：[/]")
    console.print(outline.display())

    if op_categories:
        console.print("\n[cyan]算子分类：[/]")
        for cat in op_categories:
            console.print(f"  - {cat.name}: {len(cat.operators)} 个算子")

    if not auto_confirm:
        confirm = input("\n确认继续？(y/n): ").strip().lower()
        if confirm != "y":
            console.print("[yellow]已取消[/]")
            return

    console.print("\n[bold]步骤 4/5: 生成文档内容[/]")

    writer = Writer(config.output.path, project_info.name)
    total_subsections = outline.count_subsections()
    if op_categories:
        total_subsections += len(op_categories)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("生成文档...", total=total_subsections)

        for chapter_idx, chapter in enumerate(outline.chapters, 1):
            if chapter.title == "算子参考" and op_categories:
                progress.update(task, description=f"生成: 算子参考")
                op_content_parts = []
                subsection_titles = []

                for cat in op_categories:
                    cat_md = cat.to_markdown()
                    op_content_parts.append(cat_md)
                    subsection_titles.append(cat.name)
                    progress.advance(task)

                if op_content_parts:
                    full_content = "\n\n".join(op_content_parts)
                    file_path = writer.write_section(
                        chapter_idx, chapter.title, full_content
                    )
                    console.print(f"[green]✓[/] {file_path}")
                continue

            chapter_content_parts = []
            subsection_titles = []

            for subsection in chapter.subsections:
                progress.update(
                    task, description=f"生成: {chapter.title} - {subsection.title}"
                )

                try:
                    content = await generator.generate_content(
                        chapter, subsection, project_info_str
                    )
                    chapter_content_parts.append(f"## {subsection.title}\n\n{content}")
                    subsection_titles.append(subsection.title)
                except Exception as e:
                    console.print(f"[red]✗ {subsection.title}: {e}[/]")
                    chapter_content_parts.append(f"## {subsection.title}\n\n*生成失败*")

                progress.advance(task)

            if chapter_content_parts:
                full_content = "\n\n---\n\n".join(chapter_content_parts)
                file_path = writer.write_section(
                    chapter_idx, chapter.title, full_content
                )
                console.print(f"[green]✓[/] {file_path}")

    console.print("\n[bold]步骤 5/5: 生成索引[/]")

    sections_for_index = []
    for i, c in enumerate(outline.chapters, 1):
        if c.title == "算子参考" and op_categories:
            sections_for_index.append((i, c.title, [cat.name for cat in op_categories]))
        else:
            sections_for_index.append((i, c.title, [s.title for s in c.subsections]))

    index_path = writer.write_index(sections_for_index)
    console.print(f"[green]✓[/] {index_path}")

    llm_calls = 1 + total_subsections
    console.print(
        Panel.fit(
            f"[bold green]文档生成完成！[/]\n\n"
            f"输出目录: {writer.get_output_dir()}\n"
            f"章节: {len(outline.chapters)} 个\n"
            f"子章节: {total_subsections} 个\n"
            f"LLM调用: {llm_calls} 次",
            border_style="green",
        )
    )


def display_project_info(info: ProjectInfo):
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("项目名称", info.name)
    table.add_row("语言", info.language)
    table.add_row("文件数", str(info.file_count))
    table.add_row("代码行数", f"{info.total_lines:,}")

    if info.dependencies:
        deps = ", ".join(info.dependencies[:10])
        if len(info.dependencies) > 10:
            deps += f" ... (+{len(info.dependencies) - 10})"
        table.add_row("依赖", deps)

    console.print(table)


if __name__ == "__main__":
    main()
