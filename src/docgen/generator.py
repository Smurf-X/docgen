import json
from typing import Optional, TYPE_CHECKING

from openai import AsyncOpenAI

from .config import Config
from .outline import (
    Outline,
    Chapter,
    SubSection,
    DocType,
    get_subsection_prompt,
    get_content_prompt,
    get_content_prompt_with_context,
    get_default_chapters_by_doc_type,
    DEFAULT_CHAPTERS,
)
from .scanner import Scanner
from .analyzer import CodeAnalyzer

if TYPE_CHECKING:
    from .context_builder import ContextBuilder, ChapterContext

BASE_CLASS_PATTERNS = [
    "Base",
    "Abstract",
]


def is_base_class(class_name: str, bases: list[str]) -> bool:
    for pattern in BASE_CLASS_PATTERNS:
        if pattern in class_name:
            return True
    if "ABC" in bases:
        return True
    return False


class Generator:
    def __init__(self, config: Config, scanner: Scanner, analyzer: CodeAnalyzer):
        self.config = config
        self.scanner = scanner
        self.analyzer = analyzer
        self.custom_style = ""
        self.extra_context = ""
        self.explorer = None
        self.context_builder: Optional["ContextBuilder"] = None
        self.project_name = ""

        self.client = AsyncOpenAI(
            base_url=config.llm.api_base,
            api_key=config.llm.api_key,
            timeout=config.llm.timeout,
            max_retries=config.llm.max_retries,
        )

    @property
    def doc_type(self) -> DocType:
        return self.config.doc.doc_type

    def set_explorer(self, explorer):
        self.explorer = explorer

    def set_context_builder(self, context_builder: "ContextBuilder"):
        self.context_builder = context_builder

    def set_project_name(self, name: str):
        self.project_name = name

    async def check_connection(self) -> tuple[bool, str]:
        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return True, self.config.llm.model
        except Exception as e:
            return False, str(e)

    def set_custom_style(self, style_content: str, extra_content: str = ""):
        self.custom_style = style_content
        self.extra_context = extra_content

    async def generate_subsections_for_chapter(
        self, chapter: Chapter, project_info_str: str
    ) -> list[SubSection]:
        api_chapter_titles = ["API参考", "API 参考", "内置算子使用", "核心接口定义"]
        if chapter.title in api_chapter_titles:
            return self._generate_api_subsections()

        extra_context = ""
        if self.extra_context:
            extra_context = self.extra_context

        prompt = get_subsection_prompt(
            chapter.title,
            project_info_str,
            extra_context,
            self.custom_style,
            self.doc_type,
        )
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

    def _generate_api_subsections(self) -> list[SubSection]:
        subsections = []
        seen_classes = set()

        py_files = list(self.scanner.project_path.rglob("*.py"))
        py_files = [
            f
            for f in py_files
            if not any(p.startswith(".") or p.startswith("__") for p in f.parts)
        ]
        py_files = [f for f in py_files if "test" not in str(f).lower()]

        for py_file in py_files[:20]:
            try:
                rel_path = py_file.relative_to(self.scanner.project_path)
                module_path = (
                    str(rel_path.with_suffix("")).replace("\\", ".").replace("/", ".")
                )

                if module_path.startswith("docs.") or module_path.startswith("test"):
                    continue

                info = self.analyzer.analyze_file(str(rel_path))
                if info and info.classes:
                    for cls in info.classes[:3]:
                        if cls.name not in seen_classes:
                            if self.doc_type == "user_manual":
                                if is_base_class(cls.name, list(cls.bases)):
                                    continue

                            seen_classes.add(cls.name)
                            desc = (
                                cls.docstring.split("\n")[0]
                                if cls.docstring
                                else f"{cls.name} 类"
                            )
                            subsections.append(
                                SubSection(
                                    title=cls.name,
                                    description=desc[:100],
                                    module_path=module_path,
                                    class_name=cls.name,
                                )
                            )
            except Exception:
                pass

        if not subsections:
            subsections.append(
                SubSection(
                    title="核心类",
                    description="项目核心类",
                    module_path="",
                    class_name="",
                )
            )

        return subsections[:15]

    async def generate_content(
        self, chapter: Chapter, subsection: SubSection, project_info_str: str
    ) -> str:
        api_info = ""

        if self.explorer:
            code_info = self.explorer.get_code_for_subsection(
                subsection.title,
                subsection.module_path,
                subsection.class_name,
            )
            if code_info.get("class_info") or code_info.get("examples"):
                formatted_info = self.explorer.format_code_info_for_prompt(code_info)
                if formatted_info:
                    api_info = formatted_info

        if not api_info and subsection.module_path:
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

        if chapter.title in ["安装指南", "安装与配置"]:
            deps = self.scanner._parse_dependencies()
            if deps:
                api_info = f"项目依赖：\n" + "\n".join(f"- {d}" for d in deps[:20])

        if chapter.title in ["快速开始", "快速入门"]:
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
            custom_style=self.custom_style,
        )

        return await self._call_llm(prompt)

    async def generate_content_with_context(
        self, chapter: Chapter, subsection: SubSection, project_info_str: str
    ) -> str:
        if not self.context_builder:
            return await self.generate_content(chapter, subsection, project_info_str)

        context = self.context_builder.build(
            chapter_title=chapter.title,
            chapter_description=chapter.description,
            module_path=subsection.module_path,
            class_name=subsection.class_name,
        )

        context_info = context.format_for_prompt()

        prompt = get_content_prompt_with_context(
            project_name=self.project_name or self.scanner.project_path.name,
            subsection_title=subsection.title,
            project_info=project_info_str,
            context_info=context_info,
            custom_style=self.custom_style,
            doc_type=self.doc_type,
        )

        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        if self.config.llm.stream:
            return await self._call_llm_stream(prompt)
        else:
            return await self._call_llm_sync(prompt)

    async def _call_llm_stream(self, prompt: str) -> str:
        stream = await self.client.chat.completions.create(
            model=self.config.llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            stream=True,
        )

        content = ""
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content

        return content

    async def _call_llm_sync(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.config.llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
        )
        return response.choices[0].message.content or ""

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
        user_manual_defaults = {
            "概述": [
                SubSection(title="项目简介", description="项目背景和目的"),
                SubSection(title="核心特性", description="项目的主要特性"),
                SubSection(title="适用场景", description="项目的应用场景"),
            ],
            "安装与配置": [
                SubSection(title="环境要求", description="Python版本、依赖等"),
                SubSection(title="安装步骤", description="pip install等"),
                SubSection(title="配置文件说明", description="配置文件格式"),
            ],
            "快速入门": [
                SubSection(title="Hello World", description="最简单的示例"),
                SubSection(title="基本使用流程", description="完整流程示例"),
            ],
            "内置算子使用": [
                SubSection(title="算子概览", description="内置算子列表"),
            ],
            "使用示例": [
                SubSection(title="基础示例", description="基本使用示例"),
                SubSection(title="进阶示例", description="高级使用场景"),
            ],
        }

        developer_manual_defaults = {
            "架构设计": [
                SubSection(title="整体架构", description="系统架构图和说明"),
                SubSection(title="模块职责划分", description="各模块职责"),
                SubSection(title="类继承关系图", description="类的继承关系"),
            ],
            "核心接口定义": [
                SubSection(title="BaseOperator", description="基础算子接口"),
                SubSection(title="MapperOperator", description="映射算子接口"),
            ],
            "开发自定义算子": [
                SubSection(title="开发自定义 Mapper", description="如何开发映射算子"),
                SubSection(title="开发自定义 Filter", description="如何开发过滤算子"),
            ],
            "API 参考": [
                SubSection(title="核心类", description="主要的类和接口"),
            ],
        }

        if self.doc_type == "user_manual":
            return user_manual_defaults.get(
                chapter_title, [SubSection(title="概述", description="章节概述")]
            )
        elif self.doc_type == "developer_manual":
            return developer_manual_defaults.get(
                chapter_title, [SubSection(title="概述", description="章节概述")]
            )

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
