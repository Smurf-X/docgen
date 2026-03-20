import httpx
import json
from typing import Optional
from pathlib import Path

from .config import Config
from .outline import (
    Outline,
    Section,
    SubSection,
    get_outline_prompt,
    get_section_prompt,
)
from .scanner import Scanner
from .analyzer import CodeAnalyzer


class Generator:
    def __init__(self, config: Config, scanner: Scanner, analyzer: CodeAnalyzer):
        self.config = config
        self.scanner = scanner
        self.analyzer = analyzer

    async def generate_outline(self, project_info_str: str) -> Outline:
        prompt = get_outline_prompt(project_info_str)
        response = await self._call_llm(prompt)

        try:
            json_str = self._extract_json(response)
            outline_dict = json.loads(json_str)
            return Outline.from_dict(outline_dict)
        except Exception as e:
            print(f"解析大纲失败: {e}")
            return self._get_default_outline()

    async def generate_subsection(
        self, section: Section, subsection: SubSection, project_info_str: str
    ) -> str:
        module_info = ""
        api_info = ""
        example_code = ""
        dependencies = ""

        if subsection.module_path:
            module_info = self.analyzer.get_api_summary([subsection.module_path])

            if subsection.class_name:
                class_detail = self.analyzer.get_class_details(
                    subsection.module_path, subsection.class_name
                )
                if class_detail:
                    api_info = class_detail
            else:
                all_classes = self.analyzer.get_all_classes([subsection.module_path])
                if all_classes:
                    api_info = "\n\n".join(
                        cls.to_markdown() for _, _, cls in all_classes[:3]
                    )

        if section.title == "安装指南":
            dependencies = "\n".join(
                f"- {d}" for d in self.scanner._parse_dependencies()[:20]
            )

        if section.title == "快速开始":
            entry_points = self.scanner._find_entry_points()[:2]
            for entry in entry_points:
                content = self.scanner.get_file_content(entry)
                if content:
                    example_code += f"\n# {entry}\n```python\n{content}\n```\n"

        if section.title == "使用示例":
            examples_dir = self.scanner.project_path / "examples"
            if examples_dir.exists():
                for example_file in list(examples_dir.glob("*.py"))[:2]:
                    try:
                        content = example_file.read_text(encoding="utf-8")
                        example_code += f"\n# examples/{example_file.name}\n```python\n{content}\n```\n"
                    except:
                        pass

        prompt = get_section_prompt(
            section_title=section.title,
            subsection_title=subsection.title,
            subsection_description=subsection.description,
            project_info=project_info_str,
            module_info=module_info,
            api_info=api_info,
            example_code=example_code,
            dependencies=dependencies,
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

    def _get_default_outline(self) -> Outline:
        return Outline(
            sections=[
                Section(
                    title="项目简介",
                    description="介绍项目背景和核心概念",
                    subsections=[
                        SubSection(title="项目背景", description="项目解决什么问题"),
                        SubSection(title="核心特性", description="项目的主要特性"),
                        SubSection(
                            title="核心概念", description="DocSet, Document等核心概念"
                        ),
                    ],
                ),
                Section(
                    title="架构设计",
                    description="系统架构说明",
                    subsections=[
                        SubSection(title="整体架构", description="系统架构图和说明"),
                        SubSection(title="数据流", description="数据处理流程"),
                    ],
                ),
                Section(
                    title="安装指南",
                    description="安装和配置说明",
                    subsections=[
                        SubSection(title="环境要求", description="Python版本、依赖等"),
                        SubSection(title="安装步骤", description="pip install等"),
                    ],
                ),
                Section(
                    title="快速开始",
                    description="快速上手指南",
                    subsections=[
                        SubSection(title="Hello World", description="最简单的示例"),
                        SubSection(
                            title="基本流程", description="读取-处理-写入的基本流程"
                        ),
                    ],
                ),
                Section(
                    title="使用示例",
                    description="完整的使用示例",
                    subsections=[
                        SubSection(
                            title="PDF文档处理", description="处理PDF文件的完整示例"
                        ),
                        SubSection(
                            title="RAG应用示例", description="构建RAG应用的示例"
                        ),
                    ],
                ),
                Section(
                    title="开发指南",
                    description="贡献代码指南",
                    subsections=[
                        SubSection(title="开发环境", description="搭建开发环境"),
                        SubSection(title="贡献流程", description="如何贡献代码"),
                    ],
                ),
            ]
        )
