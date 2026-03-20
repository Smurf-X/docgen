import httpx
import json
from typing import Optional
from pathlib import Path

from .config import Config
from .outline import (
    Outline,
    Chapter,
    SubSection,
    get_subsection_prompt,
    get_content_prompt,
    DEFAULT_CHAPTERS,
)
from .scanner import Scanner
from .analyzer import CodeAnalyzer


class Generator:
    def __init__(self, config: Config, scanner: Scanner, analyzer: CodeAnalyzer):
        self.config = config
        self.scanner = scanner
        self.analyzer = analyzer

    async def generate_subsections_for_chapter(
        self, chapter: Chapter, project_info_str: str
    ) -> list[SubSection]:
        extra_context = ""

        if chapter.title == "API参考":
            modules = self.scanner._identify_core_modules()
            if modules:
                extra_context = f"项目核心模块：{', '.join(modules[:15])}"

        prompt = get_subsection_prompt(chapter.title, project_info_str, extra_context)
        response = await self._call_llm(prompt)

        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            subsections = []
            for sub_data in data.get("subsections", []):
                subsections.append(SubSection.from_dict(sub_data))
            return subsections
        except Exception as e:
            print(f"解析子章节失败: {e}")
            return self._get_default_subsections(chapter.title)

    async def generate_content(
        self, chapter: Chapter, subsection: SubSection, project_info_str: str
    ) -> str:
        api_info = ""

        if subsection.module_path:
            module_info = self.analyzer.get_api_summary([subsection.module_path])

            if subsection.class_name:
                class_detail = self.analyzer.get_class_details(
                    subsection.module_path, subsection.class_name
                )
                if class_detail:
                    api_info = f"API详细信息：\n{class_detail}"
            else:
                all_classes = self.analyzer.get_all_classes([subsection.module_path])
                if all_classes:
                    api_info = f"模块信息：\n{module_info[:3000]}"

        if chapter.title == "安装指南":
            deps = self.scanner._parse_dependencies()
            if deps:
                api_info = f"项目依赖：\n" + "\n".join(f"- {d}" for d in deps[:20])

        if chapter.title == "快速开始":
            entry_points = self.scanner._find_entry_points()[:2]
            for entry in entry_points:
                content = self.scanner.get_file_content(entry)
                if content:
                    api_info += (
                        f"\n入口文件 {entry}:\n```python\n{content[:2000]}\n```\n"
                    )

        if chapter.title == "使用示例":
            examples_dir = self.scanner.project_path / "examples"
            if examples_dir.exists():
                for example_file in list(examples_dir.glob("*.py"))[:2]:
                    try:
                        content = example_file.read_text(encoding="utf-8")
                        api_info += f"\n示例 {example_file.name}:\n```python\n{content[:2000]}\n```\n"
                    except:
                        pass

        prompt = get_content_prompt(
            chapter_title=chapter.title,
            subsection_title=subsection.title,
            subsection_description=subsection.description,
            project_info=project_info_str,
            api_info=api_info,
        )

        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.config.llm.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.llm.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.llm.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.config.llm.temperature,
                    "max_tokens": self.config.llm.max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _extract_json(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:
            return text[start : end + 1]

        return text

    def _get_default_subsections(self, chapter_title: str) -> list[SubSection]:
        defaults = {
            "项目简介": [
                SubSection(title="项目背景", description="项目解决什么问题"),
                SubSection(title="核心特性", description="项目的主要特性"),
            ],
            "架构设计": [
                SubSection(title="整体架构", description="系统架构图和说明"),
                SubSection(title="核心模块", description="主要模块划分"),
            ],
            "安装指南": [
                SubSection(title="环境要求", description="Python版本、依赖等"),
                SubSection(title="安装步骤", description="pip install等"),
            ],
            "快速开始": [
                SubSection(title="Hello World", description="最简单的示例"),
                SubSection(title="基本用法", description="读取-处理-写入的基本流程"),
            ],
            "API参考": [
                SubSection(title="核心类", description="主要的类和接口"),
            ],
            "使用示例": [
                SubSection(title="基础示例", description="基本使用示例"),
                SubSection(title="进阶示例", description="高级使用场景"),
            ],
        }
        return defaults.get(chapter_title, [SubSection(title="概述")])
