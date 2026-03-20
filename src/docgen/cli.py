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
from .outline import Outline
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

    console.print("\n[bold]步骤 1/4: 扫描项目[/]")
    with console.status("[cyan]正在扫描项目...[/]"):
        scanner = Scanner(project_path, config.scan.exclude)
        project_info = scanner.scan()
        analyzer = CodeAnalyzer(project_path)

    display_project_info(project_info)

    console.print("\n[bold]步骤 2/4: 生成文档大纲[/]")
    with console.status("[cyan]正在生成文档大纲...[/]"):
        generator = Generator(config, scanner, analyzer)
        project_info_str = project_info.to_summary()
        outline = await generator.generate_outline(project_info_str)

    console.print("\n[cyan]生成的文档大纲:[/]")
    console.print(outline.display())

    subsection_count = outline.count_subsections()
    console.print(f"\n共 {len(outline.sections)} 个章节，{subsection_count} 个子章节")

    if not auto_confirm:
        confirm = input("\n确认开始生成？(y/n): ").strip().lower()
        if confirm != "y":
            console.print("[yellow]已取消[/]")
            return

    console.print("\n[bold]步骤 3/4: 生成文档内容[/]")

    writer = Writer(config.output.path, project_info.name)
    section_contents = {}
    sections_for_index = []

    total_subsections = sum(len(s.subsections) for s in outline.sections)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("生成文档...", total=total_subsections)

        for section_idx, section in enumerate(outline.sections, 1):
            section_content_parts = []
            subsection_titles = []

            for subsection in section.subsections:
                progress.update(
                    task, description=f"生成: {section.title} - {subsection.title}"
                )

                try:
                    content = await generator.generate_subsection(
                        section, subsection, project_info_str
                    )
                    section_content_parts.append(f"## {subsection.title}\n\n{content}")
                    subsection_titles.append(subsection.title)
                    progress.advance(task)
                except Exception as e:
                    console.print(f"[red]✗ 生成失败: {subsection.title} - {e}[/]")
                    section_content_parts.append(f"## {subsection.title}\n\n*生成失败*")
                    progress.advance(task)

            if section_content_parts:
                full_content = "\n\n---\n\n".join(section_content_parts)
                file_path = writer.write_section(
                    section_idx, section.title, full_content
                )
                console.print(f"[green]✓[/] {file_path}")

                sections_for_index.append(
                    (section_idx, section.title, subsection_titles)
                )

    console.print("\n[bold]步骤 4/4: 生成索引[/]")
    index_path = writer.write_index(sections_for_index)
    console.print(f"[green]✓[/] {index_path}")

    console.print(
        Panel.fit(
            f"[bold green]文档生成完成！[/]\n\n"
            f"输出目录: {writer.get_output_dir()}\n"
            f"共生成 {len(outline.sections) + 1} 个文件\n"
            f"LLM调用次数: {1 + total_subsections} 次",
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
