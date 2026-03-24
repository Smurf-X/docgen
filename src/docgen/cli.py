import sys
import io
import asyncio
import json
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
from .outline import (
    Outline,
    DEFAULT_CHAPTERS,
    OPERATOR_CHAPTERS,
    DocType,
    get_default_chapters,
    get_default_chapters_by_doc_type,
    get_outline_from_overview_prompt,
    Chapter,
    SubSection,
)
from .generator import Generator
from .writer import Writer
from .op_analyzer import OperatorAnalyzer
from .explorer import Explorer
from .structure_inferrer import StructureInferrer
from .context_builder import ContextBuilder


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
@click.option(
    "--explore",
    "-e",
    is_flag=True,
    help="启用项目探索模式，自动分析项目结构生成更精准的文档目录",
)
@click.option(
    "--structure", "-s", is_flag=True, help="启用结构注入模式，先推断项目结构再生成文档"
)
@click.option(
    "--type",
    "-t",
    "doc_type",
    type=click.Choice(["user_manual", "developer_manual"]),
    default=None,
    help="文档类型: user_manual (用户手册) 或 developer_manual (开发接口手册)",
)
def main(
    project_path: str,
    config_path: str,
    output_path: Optional[str],
    version: bool,
    yes: bool,
    explore: bool,
    structure: bool,
    doc_type: Optional[str],
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

    if doc_type:
        config.doc.doc_type = doc_type  # type: ignore

    asyncio.run(
        run_generation(project_path, config, config_path, yes, explore, structure)
    )


async def run_generation(
    project_path: str,
    config: Config,
    config_path: str,
    auto_confirm: bool,
    enable_explore: bool,
    enable_structure: bool,
):
    console.print(
        Panel.fit(
            f"[bold cyan]DocGen[/] - 文档生成工具\n版本: {__version__}",
            border_style="cyan",
        )
    )

    console.print("\n[bold]步骤 1/6: 扫描项目[/]")
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

    # 初始化 generator
    generator = Generator(config, scanner, analyzer)

    # 检查 LLM 连通性
    console.print("\n[cyan]正在检查 LLM 连接...[/]")
    is_connected, message = await generator.check_connection()
    if is_connected:
        console.print(f"[green]✓ LLM 已连接 (模型: {message})[/]")
    else:
        console.print(f"[red]✗ LLM 连接失败: {message}[/]")
        console.print("[yellow]请检查配置文件中的 api_base、api_key 和 model 设置[/]")
        return

    # 加载自定义风格指南
    style_content, extra_content = config.load_customization_content(config_path)
    if style_content:
        generator.set_custom_style(style_content, extra_content)
        console.print("[cyan]已加载自定义风格指南[/]")
    if extra_content:
        console.print("[cyan]已加载额外上下文[/]")

    project_structure = None
    context_builder = None

    if enable_structure:
        console.print("\n[bold]步骤 2/7: 推断项目结构[/]")
        console.print("[cyan]正在推断项目结构...[/]")

        inferrer = StructureInferrer(scanner, config)
        project_structure = inferrer.infer()

        console.print(f"\n[green]项目类型: {project_structure.type}[/]")
        console.print(f"\n[cyan]推断的项目结构:[/]")
        console.print(inferrer.format_structure_tree(project_structure))

        if project_structure.relations:
            console.print(f"\n[cyan]推断的模块关系:[/]")
            console.print(inferrer.format_relations(project_structure.relations))

        if not auto_confirm:
            console.print("\n[cyan]是否确认此结构？[/]")
            console.print("  [Y] 确认，继续生成文档")
            console.print("  [n] 不正确，让我手动编辑")
            console.print("  [e] 编辑描述信息")
            confirm = input("选择: ").strip().lower()

            if confirm == "n":
                console.print("[yellow]请编辑生成的 project.yaml 文件后重新运行[/]")
                docgen_dir = Path(project_path) / ".docgen"
                docgen_dir.mkdir(exist_ok=True)
                project_yaml_path = docgen_dir / "project.yaml"
                project_yaml_path.write_text(
                    project_structure.to_yaml(), encoding="utf-8"
                )
                console.print(f"[cyan]已生成: {project_yaml_path}[/]")
                return
            elif confirm == "e":
                docgen_dir = Path(project_path) / ".docgen"
                docgen_dir.mkdir(exist_ok=True)
                project_yaml_path = docgen_dir / "project.yaml"
                project_yaml_path.write_text(
                    project_structure.to_yaml(), encoding="utf-8"
                )
                console.print(f"[cyan]已生成: {project_yaml_path}[/]")
                console.print("[yellow]请编辑后重新运行[/]")
                return

        context_builder = ContextBuilder(project_structure, analyzer)
        generator.set_context_builder(context_builder)
        generator.set_project_name(project_structure.name)

        if project_structure.type != "unknown":
            project_type = project_structure.type

    overview = None
    explorer = None
    outline = None
    if enable_explore:
        console.print("\n[bold]步骤 3/7: 项目探索分析[/]")
        console.print("[cyan]正在分析项目结构...[/]")

        explorer = Explorer(config, scanner)

        # 使用批量分类方式探索（针对差 LLM 优化）
        overview = await explorer.explore_with_classification()

        # 将 explorer 传递给 generator
        generator.set_explorer(explorer)

        # 显示探索结果
        console.print(f"\n[green]项目类型: {overview.project_type}[/]")
        console.print(f"[green]项目概述: {overview.summary}[/]")

        if overview.core_modules:
            console.print("\n[cyan]核心模块:[/]")
            for module in overview.core_modules[:5]:
                classes_str = ", ".join(module.get("classes", [])[:3])
                console.print(
                    f"  - {module['path']}: {module['summary']} ({classes_str}...)"
                )

        # 更新项目类型
        if overview.project_type != "general":
            project_type = overview.project_type

        # 直接从分类结果生成目录（不需要额外 LLM 调用）
        console.print(f"\n[bold]步骤 4/7: 生成文档目录[/]")
        console.print("[cyan]基于分类结果生成文档目录...[/]")

        classifications = explorer.get_classifications()
        if classifications:
            outline = explorer.generate_outline_from_classification(classifications)
            console.print("[green]✓ 已生成文档目录[/]")
            console.print(f"[cyan]生成的目录结构:[/]")
            console.print(outline.display())
        else:
            outline = None

    # 如果探索模式没有生成目录，使用默认方式
    if not outline:
        step_num = "5/7" if enable_explore or enable_structure else "4/7"
        console.print(f"\n[bold]步骤 {step_num}: 确认章节[/]")

        doc_type = config.doc.doc_type
        if doc_type in ["user_manual", "developer_manual"]:
            default_chapters = get_default_chapters_by_doc_type(doc_type)
            doc_type_name = "用户手册" if doc_type == "user_manual" else "开发接口手册"
            console.print(f"[cyan]文档类型: {doc_type_name}[/]")
        else:
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

    console.print(f"\n[green]已选择 {len(outline.chapters)} 个章节[/]")

    console.print(f"\n[bold]步骤 6/7: 生成子章节[/]")

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

            # 如果子章节已经生成（探索模式），跳过
            if chapter.subsections:
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

    console.print(f"\n[bold]步骤 7/7: 生成文档内容[/]")

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
                    if context_builder:
                        content = await generator.generate_content_with_context(
                            chapter, subsection, project_info_str
                        )
                    else:
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

    console.print(f"\n[bold]步骤 8/8: 生成索引[/]")

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


async def generate_outline_from_overview(
    generator: Generator, overview, custom_style: str = ""
) -> Optional[Outline]:
    """基于项目全貌生成文档目录"""
    from .explorer import Explorer

    explorer = Explorer(generator.config, generator.scanner)
    overview_content = explorer.format_overview_for_prompt(overview)

    prompt = get_outline_from_overview_prompt(overview_content, custom_style)

    try:
        if generator.config.llm.stream:
            response = await generator._call_llm_stream(prompt)
        else:
            response = await generator._call_llm_sync(prompt)

        # 提取 JSON
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        data = json.loads(json_str.strip())

        outline = Outline()
        for chapter_data in data.get("chapters", []):
            chapter = Chapter(
                title=chapter_data.get("title", ""),
                description=chapter_data.get("description", ""),
            )
            for sub_data in chapter_data.get("subsections", []):
                chapter.subsections.append(
                    SubSection(
                        title=sub_data.get("title", ""),
                        description=sub_data.get("description", ""),
                        module_path=sub_data.get("module_path", ""),
                        class_name=sub_data.get("class_name", ""),
                    )
                )
            outline.chapters.append(chapter)

        return outline

    except Exception as e:
        print(f"基于项目全貌生成目录失败: {e}")
        return None


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
