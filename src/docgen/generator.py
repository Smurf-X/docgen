import json
import os
from typing import Optional, TYPE_CHECKING

from openai import AsyncOpenAI

from .config import Config
from .outline import (
    Outline,
    Chapter,
    SubSection,
    get_subsection_prompt,
    get_content_prompt,
    get_content_prompt_with_context,
    DEFAULT_CHAPTERS,
)
from .scanner import Scanner
from .analyzer import CodeAnalyzer

if TYPE_CHECKING:
    from .context_builder import ContextBuilder, ChapterContext


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
        api_chapter_titles = [
            "API参考",
            "API 参考",
            "内置算子参考",
            "内置算子使用",
            "使用内置算子",
        ]
        if chapter.title in api_chapter_titles:
            return self._generate_api_subsections()

        dev_chapter_titles = ["自定义算子开发", "自定义算子开发与使用", "开发指南"]
        if chapter.title in dev_chapter_titles:
            return self._generate_dev_subsections()

        extra_context = ""
        if self.extra_context:
            extra_context = self.extra_context

        prompt = get_subsection_prompt(
            chapter.title,
            project_info_str,
            extra_context,
            self.custom_style,
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
        operators = self.analyzer.scan_registered_operators()

        from collections import defaultdict

        by_category = defaultdict(list)
        for op in operators:
            by_category[op.category].append(op)

        processing_categories = ["text", "audio", "image", "video"]
        storage_categories = ["datasource", "datasink"]

        processing_children = []
        for category in processing_categories:
            if category not in by_category:
                continue
            ops = by_category[category]
            category_name = ops[0].category_display if ops else category
            operators_data = [
                {
                    "register_name": op.register_name,
                    "class_name": op.class_name,
                    "module_path": op.module_path,
                    "file_path": op.file_path,
                }
                for op in ops
            ]
            processing_children.append(
                SubSection(
                    title=category_name,
                    description=f"{category_name}，共 {len(ops)} 个算子",
                    operators=operators_data,
                )
            )

        storage_children = []
        for category in storage_categories:
            if category not in by_category:
                continue
            ops = by_category[category]
            category_name = ops[0].category_display if ops else category
            operators_data = [
                {
                    "register_name": op.register_name,
                    "class_name": op.class_name,
                    "module_path": op.module_path,
                    "file_path": op.file_path,
                }
                for op in ops
            ]
            storage_children.append(
                SubSection(
                    title=category_name,
                    description=f"{category_name}，共 {len(ops)} 个算子",
                    operators=operators_data,
                )
            )

        subsections = []
        if processing_children:
            subsections.append(
                SubSection(
                    title="多模态数据处理算子",
                    description="文本、音频、图像、视频等模态的数据处理算子",
                    children=processing_children,
                )
            )
        if storage_children:
            subsections.append(
                SubSection(
                    title="数据存储与落盘",
                    description="数据读取和写入相关算子",
                    children=storage_children,
                )
            )

        if not subsections:
            subsections.append(
                SubSection(
                    title="核心算子",
                    description="项目核心算子",
                )
            )

        return subsections

    def _generate_dev_subsections(self) -> list[SubSection]:
        """生成自定义算子开发章节的子章节"""
        base_classes = self._scan_base_classes()

        mapper_children = []
        connector_children = []

        for bc in base_classes:
            if bc["category"] == "mapper":
                mapper_children.append(
                    SubSection(
                        title=bc["class_name"],
                        description=bc["docstring"][:100]
                        if bc["docstring"]
                        else f"{bc['class_name']} 基类",
                        module_path=bc["module_path"],
                        class_name=bc["class_name"],
                    )
                )
            elif bc["category"] in ["datasource", "datasink"]:
                connector_children.append(
                    SubSection(
                        title=bc["class_name"],
                        description=bc["docstring"][:100]
                        if bc["docstring"]
                        else f"{bc['class_name']} 基类",
                        module_path=bc["module_path"],
                        class_name=bc["class_name"],
                    )
                )

        subsections = []

        subsections.append(
            SubSection(
                title="开发流程概述",
                description="自定义算子的开发、注册、使用流程",
            )
        )

        if mapper_children:
            subsections.append(
                SubSection(
                    title="数据处理算子开发",
                    description="继承 Mapper 等基类开发自定义算子",
                    children=mapper_children,
                )
            )

        if connector_children:
            subsections.append(
                SubSection(
                    title="DataSource 与 DataSink 开发",
                    description="开发自定义数据读取和写入算子",
                    children=connector_children,
                )
            )

        subsections.append(
            SubSection(
                title="在 YAML 中使用自定义算子",
                description="如何配置自定义算子路径并使用",
            )
        )

        return subsections

    def _scan_base_classes(self) -> list[dict]:
        """扫描基类文件，提取接口信息"""
        base_classes = []

        base_patterns = [
            ("base_op.py", ["MapperOperator", "FilterOperator", "ConnectorOperator"]),
            ("mapper", ["MapperOperator", "BaseMapper"]),
            ("connector", ["DataSource", "DataSink", "ConnectorOperator"]),
        ]

        py_files = list(self.scanner.project_path.rglob("*.py"))

        for py_file in py_files:
            try:
                rel_path = py_file.relative_to(self.scanner.project_path)
                module_path = (
                    str(rel_path.with_suffix("")).replace(os.sep, ".").replace("/", ".")
                )

                if "base" not in str(rel_path).lower():
                    continue
                if module_path.startswith("docs.") or module_path.startswith("test"):
                    continue

                info = self.analyzer.analyze_file(str(rel_path))
                if info and info.classes:
                    for cls in info.classes:
                        if (
                            "Base" in cls.name
                            or "ABC" in cls.bases
                            or cls.name.endswith("Operator")
                        ):
                            category = self._get_base_class_category(
                                cls.name, cls.bases
                            )
                            base_classes.append(
                                {
                                    "class_name": cls.name,
                                    "module_path": module_path,
                                    "file_path": str(rel_path),
                                    "bases": list(cls.bases),
                                    "docstring": cls.docstring,
                                    "methods": [
                                        {
                                            "name": m.name,
                                            "parameters": [
                                                str(p) for p in m.parameters
                                            ],
                                            "return_type": m.return_type,
                                            "docstring": m.docstring,
                                        }
                                        for m in cls.methods
                                    ],
                                    "category": category,
                                }
                            )
            except Exception:
                pass

        return base_classes

    def _get_base_class_category(self, class_name: str, bases: list[str]) -> str:
        """判断基类类别"""
        name_lower = class_name.lower()
        bases_str = " ".join(bases).lower()

        if "mapper" in name_lower or "mapper" in bases_str:
            return "mapper"
        if "datasource" in name_lower or "datasource" in bases_str:
            return "datasource"
        if "datasink" in name_lower or "datasink" in bases_str:
            return "datasink"
        if "connector" in name_lower or "connector" in bases_str:
            return "connector"
        if "filter" in name_lower:
            return "filter"

        return "other"

    async def generate_operator_content(
        self, operator_info: dict, project_info_str: str
    ) -> str:
        """
        为单个算子生成文档（调用 LLM）

        :param operator_info: 算子信息，包含 register_name, class_name, module_path, file_path
        :param project_info_str: 项目信息
        :return: 生成的文档内容
        """
        module_path = operator_info["module_path"]
        class_name = operator_info["class_name"]
        register_name = operator_info["register_name"]
        file_path = operator_info["file_path"]

        operators = self.analyzer.scan_registered_operators()
        op = next((o for o in operators if o.register_name == register_name), None)

        code_context = ""
        if op and op.class_info:
            cls = op.class_info
            code_context = f"## 算子代码信息\n\n"
            code_context += f"**类名**: {cls.name}\n"
            code_context += f"**注册名称**: {register_name}\n\n"

            if cls.bases:
                code_context += f"**继承自**: {', '.join(cls.bases)}\n\n"

            if cls.docstring:
                code_context += f"**类说明**:\n{cls.docstring.strip()}\n\n"

            if cls.methods:
                code_context += "**方法**:\n"
                for method in cls.methods[:8]:
                    params_str = ", ".join(str(p) for p in method.parameters[:5])
                    method_sig = f"- `{method.name}({params_str})`"
                    if method.return_type:
                        method_sig += f" -> {method.return_type}"
                    code_context += method_sig + "\n"
                    if method.docstring:
                        code_context += f"  {method.docstring[:150]}\n"
                code_context += "\n"

        full_file_path = self.scanner.project_path / file_path
        if full_file_path.exists():
            try:
                with open(full_file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                code_context += f"**完整代码**:\n```python\n{file_content}\n```\n"
            except Exception:
                pass

        prompt = f"""你是一个技术文档专家。请为以下算子撰写用户手册文档。

{code_context}

## 项目信息

{project_info_str}

## 写作要求

1. 用中文撰写，语言简洁清晰
2. 重点介绍用户需要知道的内容：如何使用、参数说明、使用示例
3. 不要介绍继承关系、基类实现等开发细节
4. 提供 YAML 配置示例
5. 使用 Markdown 格式

## 输出格式

直接输出文档内容，不要包含标题（标题会自动添加）。
"""

        return await self._call_llm(prompt)

    async def generate_content(
        self, chapter: Chapter, subsection: SubSection, project_info_str: str
    ) -> str:
        if subsection.operators:
            parts = []
            for op_info in subsection.operators:
                content = await self.generate_operator_content(
                    op_info, project_info_str
                )
                parts.append(content)
            return "\n\n---\n\n".join(parts)

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
        defaults = {
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
            "Pipeline 使用指南": [
                SubSection(
                    title="PipelineBuilder 使用方法", description="创建和执行Pipeline"
                ),
                SubSection(title="YAML 配置格式详解", description="配置文件格式"),
                SubSection(title="算子编排与执行", description="如何编排算子"),
                SubSection(title="输入输出处理", description="数据处理"),
            ],
            "内置算子参考": [
                SubSection(title="文本分块算子", description="文本分块相关算子"),
                SubSection(title="文本嵌入算子", description="文本嵌入相关算子"),
                SubSection(title="图像处理算子", description="图像处理相关算子"),
                SubSection(title="音频处理算子", description="音频处理相关算子"),
                SubSection(title="连接器算子", description="数据连接器算子"),
            ],
            "自定义算子开发": [
                SubSection(title="开发流程概述", description="整体开发流程"),
                SubSection(title="开发自定义 Mapper", description="如何开发映射算子"),
                SubSection(title="开发自定义 Connector", description="如何开发连接器"),
                SubSection(title="开发底层 Function", description="如何开发底层功能"),
                SubSection(title="注册与使用自定义算子", description="注册和使用流程"),
            ],
            "常见问题": [
                SubSection(title="安装问题", description="安装相关问题"),
                SubSection(title="配置问题", description="配置相关问题"),
                SubSection(title="使用问题", description="使用相关问题"),
            ],
            "项目简介": [
                SubSection(title="项目背景", description="项目解决什么问题"),
                SubSection(title="核心特性", description="项目的主要特性"),
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
