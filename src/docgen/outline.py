from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .explorer import ProjectOverview


DEFAULT_CHAPTERS = [
    "概述",
    "安装与配置",
    "快速入门",
    "Pipeline 使用指南",
    "内置算子参考",
    "自定义算子开发",
    "常见问题",
]


OPERATOR_CHAPTERS = [
    "项目简介",
    "核心概念",
    "安装指南",
    "快速开始",
    "配置说明",
    "算子参考",
    "使用示例",
]


def get_default_chapters(project_type: str = "general") -> list[str]:
    if project_type == "operator":
        return OPERATOR_CHAPTERS.copy()
    elif project_type == "operator_framework":
        return DEFAULT_CHAPTERS.copy()
    return DEFAULT_CHAPTERS.copy()


@dataclass
class SubSection:
    title: str
    description: str = ""
    module_path: str = ""
    class_name: str = ""
    operators: list = field(default_factory=list)
    children: list["SubSection"] = field(default_factory=list)

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "operators": self.operators,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubSection":
        children = [cls.from_dict(c) for c in data.get("children", [])]
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            module_path=data.get("module_path", ""),
            class_name=data.get("class_name", ""),
            operators=data.get("operators", []),
            children=children,
        )


@dataclass
class Chapter:
    title: str
    description: str = ""
    subsections: list[SubSection] = field(default_factory=list)

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "subsections": [s.to_dict() for s in self.subsections],
        }


@dataclass
class Outline:
    chapters: list[Chapter] = field(default_factory=list)

    def display(self) -> str:
        lines = []
        for i, chapter in enumerate(self.chapters, 1):
            lines.append(f"{i}. {chapter.title}")
            for j, sub in enumerate(chapter.subsections, 1):
                lines.append(f"   {i}.{j} {sub.title}")
                for k, child in enumerate(sub.children, 1):
                    lines.append(f"      {i}.{j}.{k} {child.title}")
        return "\n".join(lines)

    def count_subsections(self) -> int:
        count = 0
        for chapter in self.chapters:
            for sub in chapter.subsections:
                if sub.children:
                    count += len(sub.children)
                else:
                    count += 1
        return count

    @classmethod
    def from_chapter_titles(cls, titles: list[str]) -> "Outline":
        outline = cls()
        for title in titles:
            outline.chapters.append(Chapter(title=title))
        return outline


SUBSECTION_PROMPT_TEMPLATE = """你是一个技术文档专家。请根据以下项目信息，为"{chapter_title}"章节生成子章节列表。

项目信息：
{project_info}

{extra_context}

要求：
1. 子章节应该具体、有针对性，标题简洁明了
2. 每个子章节应该有明确的主题
3. 如果是算子相关的章节，请指定module_path和class_name
4. 子节数量控制在 2-8 个
5. 子章节标题不要与主章节标题重复

【严重警告 - 禁止编造】
- class_name 必须是项目中实际存在的类名
- 如果不知道确切的类名，请留空，不要编造
- 禁止猜测或推断类名，必须使用项目信息中提供的实际类名

输出JSON格式：
{{
  "subsections": [
    {{"title": "子章节标题", "description": "简短描述", "module_path": "模块路径", "class_name": "类名"}}
  ]
}}

重要：
- 只输出JSON，不要有其他内容
- title 和 description 要简洁，不要包含换行或特殊字符
"""


CHAPTER_PROMPTS = {
    "概述": """这个章节介绍项目的背景、目的和核心概念。
请生成如：项目简介、核心特性、适用场景等子章节。""",
    "安装与配置": """这个章节介绍如何安装和配置。
请生成如：环境要求、安装步骤、配置文件说明等子章节。""",
    "快速入门": """这个章节帮助用户快速上手。
请生成如：Hello World、基本使用流程等子章节。
【重要】提供简单易懂的示例，让用户能快速运行起来。""",
    "Pipeline 使用指南": """这个章节介绍如何使用 Pipeline 编排数据处理流程。
请生成如：PipelineBuilder 使用方法、YAML 配置格式详解、算子编排与执行、输入输出处理等子章节。
【重要】详细介绍YAML配置文件的格式和各字段的含义。""",
    "内置算子参考": """这个章节介绍项目提供的内置算子，按功能分类。
请根据实际代码生成子章节，每个子章节对应一类算子（如文本分块算子、文本嵌入算子、图像处理算子、音频处理算子、连接器算子等）。
【重要】每个子章节介绍该类算子的功能、参数、返回值和YAML配置方法。
【重要】只介绍用户可以直接使用的具体算子，不要介绍抽象基类。""",
    "自定义算子开发": """这个章节指导开发者如何开发和使用自定义算子。
请生成如：开发流程概述、开发自定义 Mapper、开发自定义 Connector、开发底层 Function、注册与使用自定义算子等子章节。
【重要】提供完整的开发步骤、代码示例和配置示例。""",
    "常见问题": """这个章节收集用户常见问题。
请生成如：安装问题、配置问题、使用问题等子章节。""",
    "项目简介": """这个章节介绍项目的背景、目的和核心概念。
请生成如：项目背景、核心特性、核心概念等子章节。""",
    "架构设计": """这个章节介绍系统架构。
请生成如：整体架构、数据流、核心模块等子章节。""",
    "安装指南": """这个章节介绍如何安装和配置。
请生成如：环境要求、安装步骤、配置说明等子章节。""",
    "快速开始": """这个章节帮助用户快速上手。
请生成如：Hello World、基本用法、常见场景等子章节。""",
    "API参考": """这个章节介绍项目的API。
请根据项目结构，按模块分类生成子章节。
每个子章节应对应一个模块或一组相关类。
请务必填写module_path字段，指向模块路径。""",
    "使用示例": """这个章节提供完整的使用示例。
请生成如：基础示例、进阶示例、常见场景等子章节。""",
    "开发指南": """这个章节帮助开发者贡献代码。
请生成如：开发环境、测试指南、贡献流程等子章节。""",
    "核心概念": """这个章节介绍项目的核心概念和术语。
请生成如：数据模型、处理流程、执行引擎等子章节。
重点解释用户需要理解的关键概念。""",
    "配置说明": """这个章节介绍项目配置。
请生成如：配置文件格式、常用配置项、高级配置等子章节。""",
    "算子参考": """这个章节介绍数据处理算子。
请根据算子功能分类生成子章节，如：文本处理、图像处理、数据过滤等。
不需要填写module_path，算子详情会自动生成。""",
}


def get_chapter_prompt(chapter_title: str) -> str:
    return CHAPTER_PROMPTS.get(chapter_title, "")


CONTENT_PROMPT_TEMPLATE = """你是一个技术文档专家。请为以下项目生成"{subsection_title}"的内容。

项目信息：
{project_info}

章节：{chapter_title}
子章节：{subsection_title}
描述：{subsection_description}

{api_info}

要求：
1. 用中文撰写，语言简洁清晰
2. 内容要完整、准确、实用
3. 如果是API文档，请包含参数说明、返回值、使用示例
4. 如果是教程，请提供可运行的代码示例
5. 使用Markdown格式

重要格式要求：
- 【禁止】在开头输出任何标题（包括一级标题#或二级标题##），子章节标题会由系统自动添加
- 【禁止】在内容开头重复输出"### {subsection_title}"或类似标题
- 【允许】使用三级标题（### 标题）及以下层级来组织内容，但标题内容不要与子章节名称相同
- 直接开始写内容，不要先写概述性标题
- 只使用上面提供的项目信息和API信息，不要编造不存在的API或功能
- 代码示例中的导入语句和API调用必须是真实存在的

直接输出Markdown内容，不要用代码块包裹整个内容：
"""


def get_subsection_prompt(
    chapter_title: str,
    project_info: str,
    extra_context: str = "",
    custom_style: str = "",
) -> str:
    chapter_context = get_chapter_prompt(chapter_title)
    full_context = (
        f"{chapter_context}\n\n{extra_context}" if extra_context else chapter_context
    )

    style_section = ""
    if custom_style:
        style_section = f"\n\n用户自定义风格要求:\n{custom_style}"

    return (
        SUBSECTION_PROMPT_TEMPLATE.format(
            chapter_title=chapter_title,
            project_info=project_info,
            extra_context=full_context,
        )
        + style_section
    )


def get_content_prompt(
    chapter_title: str,
    subsection_title: str,
    subsection_description: str,
    project_info: str,
    api_info: str = "",
    custom_style: str = "",
) -> str:
    base_prompt = CONTENT_PROMPT_TEMPLATE.format(
        subsection_title=subsection_title,
        subsection_description=subsection_description,
        chapter_title=chapter_title,
        project_info=project_info,
        api_info=api_info if api_info else "（无额外API信息）",
    )

    if custom_style:
        base_prompt += f"\n\n用户自定义风格要求:\n{custom_style}"

    return base_prompt


OUTLINE_FROM_OVERVIEW_PROMPT = """你是一个技术文档专家。请根据以下项目全貌，生成合理的文档目录结构。

{overview_content}

要求：
1. 目录要覆盖所有核心功能，不要遗漏重要模块
2. 按用户使用顺序排列（入门 → 核心功能 → 进阶）
3. 每个章节要有针对性，标题简洁明了
4. 子章节要具体，对应具体的模块或功能
5. 对于算子类项目，每个核心模块应该有对应的章节

输出 JSON 格式：
{{
  "chapters": [
    {{
      "title": "章节标题",
      "description": "章节简介",
      "subsections": [
        {{
          "title": "子章节标题",
          "description": "子章节简介",
          "module_path": "对应的模块路径（如果有）",
          "class_name": "对应的类名（如果有）"
        }}
      ]
    }}
  ]
}}

重要：
- 只输出 JSON，不要有其他内容
- 章节数量控制在 5-10 个
- 每个章节的子节数量控制在 2-8 个
"""


def get_outline_from_overview_prompt(
    overview_content: str, custom_style: str = ""
) -> str:
    prompt = OUTLINE_FROM_OVERVIEW_PROMPT.format(overview_content=overview_content)

    if custom_style:
        prompt += f"\n\n用户自定义风格要求:\n{custom_style}"

    return prompt


CONTENT_PROMPT_WITH_CONTEXT = """你正在为项目 "{project_name}" 撰写文档的 "{subsection_title}" 部分。

{context_info}

## 项目基本信息

{project_info}

## 写作要求

1. 用中文撰写，语言简洁清晰
2. 内容要完整、准确、实用
3. 使用Markdown格式

## 【严重警告】禁止编造

4. 【绝对禁止】编造任何不存在于"代码详情"中的类名、方法名、参数或返回值
5. 【绝对禁止】猜测或推断API签名，必须完全使用"代码详情"中提供的信息
6. 【绝对禁止】使用任何未在"代码详情"中出现的类名或方法名
7. 如果"代码详情"中没有提供某个API的信息，请写"具体API请参考源码"，不要自己编造
8. 代码示例必须使用"代码详情"中真实存在的类和方法签名

重要格式要求：
- 【禁止】在开头输出任何标题，标题会由系统自动添加
- 直接开始写内容

请输出内容：
"""


def get_content_prompt_with_context(
    project_name: str,
    subsection_title: str,
    project_info: str,
    context_info: str,
    custom_style: str = "",
) -> str:
    base_prompt = CONTENT_PROMPT_WITH_CONTEXT.format(
        project_name=project_name,
        subsection_title=subsection_title,
        project_info=project_info,
        context_info=context_info,
    )

    if custom_style:
        base_prompt += f"\n\n用户自定义风格要求:\n{custom_style}"

    return base_prompt
