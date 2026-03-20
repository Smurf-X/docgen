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
from .outline import Outline, DEFAULT_CHAPTERS
from .generator import Generator
from .writer import Writer


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

    display_project_info(project_info)

    console.print("\n[bold]步骤 2/5: 确认章节[/]")
    console.print("默认章节：")
    for i, chapter in enumerate(DEFAULT_CHAPTERS, 1):
        console.print(f"  {i}. {chapter}")

    if not auto_confirm:
        console.print(
            "\n[cyan]提示：直接回车使用默认章节，或输入自定义章节（逗号分隔）[/]"
        )
        user_input = input("章节列表: ").strip()

        if user_input:
            chapters = [c.strip() for c in user_input.split(",") if c.strip()]
        else:
            chapters = DEFAULT_CHAPTERS.copy()
    else:
        chapters = DEFAULT_CHAPTERS.copy()

    outline = Outline.from_chapter_titles(chapters)
    console.print(f"\n[green]已选择 {len(chapters)} 个章节[/]")

    console.print("\n[bold]步骤 3/5: 生成子章节[/]")

    generator = Generator(config, scanner, analyzer)
    project_info_str = project_info.to_summary()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for chapter in outline.chapters:
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

    if not auto_confirm:
        confirm = input("\n确认继续？(y/n): ").strip().lower()
        if confirm != "y":
            console.print("[yellow]已取消[/]")
            return

    console.print("\n[bold]步骤 4/5: 生成文档内容[/]")

    writer = Writer(config.output.path, project_info.name)
    total_subsections = outline.count_subsections()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("生成文档...", total=total_subsections)

        for chapter_idx, chapter in enumerate(outline.chapters, 1):
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

    sections_for_index = [
        (i, c.title, [s.title for s in c.subsections])
        for i, c in enumerate(outline.chapters, 1)
    ]
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
