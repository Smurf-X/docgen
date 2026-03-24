from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .explorer import ProjectOverview


DEFAULT_CHAPTERS = [
    "项目简介",
    "架构设计",
    "安装指南",
    "快速开始",
    "API参考",
    "使用示例",
]

USER_MANUAL_CHAPTERS = [
    "概述",
    "安装与配置",
    "快速入门",
    "Pipeline 使用指南",
    "内置算子使用",
    "使用示例",
    "常见问题",
]

DEVELOPER_MANUAL_CHAPTERS = [
    "架构设计",
    "核心接口定义",
    "开发自定义算子",
    "注册机制",
    "API 参考",
    "扩展开发最佳实践",
]

DocType = Literal["user_manual", "developer_manual"]


def get_default_chapters_by_doc_type(doc_type: DocType) -> list[str]:
    if doc_type == "user_manual":
        return USER_MANUAL_CHAPTERS.copy()
    elif doc_type == "developer_manual":
        return DEVELOPER_MANUAL_CHAPTERS.copy()
    return DEFAULT_CHAPTERS.copy()


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
    elif project_type == "data_processing":
        return [
            "项目简介",
            "核心概念",
            "安装指南",
            "快速开始",
            "数据处理算子",
            "使用示例",
        ]
    elif project_type == "etl_pipeline":
        return [
            "项目简介",
            "核心概念",
            "安装指南",
            "快速开始",
            "Pipeline 编排",
            "算子参考",
            "使用示例",
        ]
    return DEFAULT_CHAPTERS.copy()


@dataclass
class SubSection:
    title: str
    description: str = ""
    module_path: str = ""
    class_name: str = ""

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "module_path": self.module_path,
            "class_name": self.class_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubSection":
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            module_path=data.get("module_path", ""),
            class_name=data.get("class_name", ""),
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

    @classmethod
    def from_dict(cls, data: dict) -> "Chapter":
        chapter = cls(
            title=data.get("title", ""), description=data.get("description", "")
        )
        for sub_data in data.get("subsections", []):
            chapter.subsections.append(SubSection.from_dict(sub_data))
        return chapter


@dataclass
class Outline:
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self):
        return {"chapters": [c.to_dict() for c in self.chapters]}

    @classmethod
    def from_dict(cls, data: dict) -> "Outline":
        outline = cls()
        for chapter_data in data.get("chapters", []):
            outline.chapters.append(Chapter.from_dict(chapter_data))
        return outline

    @classmethod
    def from_chapter_titles(cls, titles: list[str]) -> "Outline":
        outline = cls()
        for title in titles:
            outline.chapters.append(Chapter(title=title))
        return outline

    def get_chapter_titles(self) -> list[str]:
        return [c.title for c in self.chapters]

    def set_chapter_titles(self, titles: list[str]):
        old_chapters = {c.title: c for c in self.chapters}
        self.chapters = []
        for title in titles:
            if title in old_chapters:
                self.chapters.append(old_chapters[title])
            else:
                self.chapters.append(Chapter(title=title))

    def display(self, show_subsections: bool = True) -> str:
        lines = []
        for i, chapter in enumerate(self.chapters, 1):
            lines.append(f"{i}. {chapter.title}")
            if show_subsections:
                for j, sub in enumerate(chapter.subsections, 1):
                    extra = (
                        f" ({sub.module_path}/{sub.class_name})"
                        if sub.module_path or sub.class_name
                        else ""
                    )
                    lines.append(f"   {i}.{j} {sub.title}{extra}")
        return "\n".join(lines)

    def count_subsections(self) -> int:
        return sum(len(c.subsections) for c in self.chapters)


SUBSECTION_PROMPT_TEMPLATE = """你是一个技术文档专家。请根据以下项目信息，为"{chapter_title}"章节生成子章节列表。

项目信息：
{project_info}

{extra_context}

要求：
1. 子章节应该具体、有针对性，标题简洁明了
2. 每个子章节应该有明确的主题
3. 如果是API相关的章节，请指定module_path（模块路径，如 sycamore/document）和class_name（类名）
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
    "项目简介": """这个章节介绍项目的背景、目的和核心概念。
请生成如：项目背景、核心特性、核心概念等子章节。""",
    "架构设计": """这个章节介绍系统架构。
请生成如：整体架构、数据流、核心模块等子章节。
如果项目有特殊的技术组件，请包含相关子章节。""",
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
重点解释用户需要理解的关键概念，避免深入技术细节。""",
    "配置说明": """这个章节介绍项目配置。
请生成如：配置文件格式、常用配置项、高级配置等子章节。""",
    "算子参考": """这个章节介绍数据处理算子。
请根据算子功能分类生成子章节，如：文本处理、图像处理、数据过滤等。
不需要填写module_path，算子详情会自动生成。""",
}

USER_MANUAL_CHAPTER_PROMPTS = {
    "概述": """这个章节介绍项目的背景、目的和核心概念。
请生成如：项目简介、核心特性、适用场景等子章节。
【重要】这是用户手册，只关注用户需要了解的内容，不要涉及开发细节。""",
    "安装与配置": """这个章节介绍如何安装和配置。
请生成如：环境要求、安装步骤、配置文件说明等子章节。""",
    "快速入门": """这个章节帮助用户快速上手。
请生成如：Hello World、基本使用流程等子章节。
【重要】提供简单易懂的示例，让用户能快速运行起来。""",
    "Pipeline 使用指南": """这个章节介绍如何使用 Pipeline 编排数据处理流程。
请生成如：PipelineBuilder 使用方法、YAML 配置格式、算子编排等子章节。
【重要】只介绍如何配置和使用，不涉及开发细节。""",
    "内置算子使用": """这个章节介绍项目提供的内置算子，按功能分类。
请根据实际代码生成子章节，每个子章节对应一类算子（如文本处理、图像处理等）。
【重要】只介绍用户可以直接使用的具体算子，不要介绍抽象基类。
【重要】每个子章节的class_name必须填写用户可使用的具体类名。""",
    "使用示例": """这个章节提供完整的使用示例。
请生成如：文本处理流水线、多模态数据处理、自定义配置场景等子章节。""",
    "常见问题": """这个章节收集用户常见问题。
请生成如：安装问题、配置问题、使用问题等子章节。""",
}

DEVELOPER_MANUAL_CHAPTER_PROMPTS = {
    "架构设计": """这个章节介绍系统架构和模块职责。
请生成如：整体架构、模块职责划分、类继承关系图等子章节。
【重要】这是开发者手册，需要深入技术细节，说明模块间的关系。""",
    "核心接口定义": """这个章节介绍项目的核心接口和抽象类。
请生成如：BaseOperator 接口、MapperOperator 接口、FilterOperator 接口等子章节。
【重要】必须介绍所有抽象基类，说明抽象方法、继承关系。
【重要】每个子章节的class_name应该填写基类名，让开发者理解接口定义。""",
    "开发自定义算子": """这个章节指导开发者如何开发自定义算子。
请生成如：开发自定义 Mapper、开发自定义 Filter、开发自定义 Connector、开发底层 Function 等子章节。
【重要】提供扩展开发的具体步骤和代码示例。""",
    "注册机制": """这个章节介绍算子注册和发现机制。
请生成如：OperatorRegistry 使用、算子注册与发现、YAML 配置扩展等子章节。""",
    "API 参考": """这个章节提供完整的 API 参考。
请根据项目结构，按模块分类生成子章节。
【重要】包含所有类（包括基类），提供完整的接口签名。
每个子章节应对应一个模块或一个类。""",
    "扩展开发最佳实践": """这个章节介绍扩展开发的最佳实践。
请生成如：代码规范、测试指南、贡献流程等子章节。""",
}


def get_chapter_prompt(chapter_title: str, doc_type: DocType = "user_manual") -> str:
    if doc_type == "user_manual":
        return USER_MANUAL_CHAPTER_PROMPTS.get(chapter_title, "")
    elif doc_type == "developer_manual":
        return DEVELOPER_MANUAL_CHAPTER_PROMPTS.get(chapter_title, "")
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
    doc_type: DocType = "user_manual",
) -> str:
    chapter_context = get_chapter_prompt(chapter_title, doc_type)
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

    # 添加自定义风格指南
    if custom_style:
        base_prompt += f"\n\n用户自定义风格要求:\n{custom_style}"

    return base_prompt


# 基于项目全貌生成文档目录的 Prompt
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
    """生成基于项目全貌的文档目录 prompt"""
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

USER_MANUAL_CONTENT_PROMPT = """你正在为项目 "{project_name}" 撰写用户手册的 "{subsection_title}" 部分。

{context_info}

## 项目基本信息

{project_info}

## 写作要求（用户手册）

1. 用中文撰写，语言简洁清晰，面向使用者而非开发者
2. 内容要完整、准确、实用
3. 使用Markdown格式
4. 重点：如何配置、如何使用、参数说明、示例代码

## 【用户手册特别要求】

5. 【重要】这是用户手册，只介绍用户可以直接使用的具体类和算子
6. 【禁止】介绍抽象基类（如 BaseOperator, MapperOperator 等带"Base"或"ABC"的类）
7. 【禁止】介绍如何开发自定义类或扩展功能
8. 【禁止】说明类的继承关系或抽象方法
9. 用户只需要知道：这个类是什么、怎么创建、有什么参数、怎么调用
10. 如果提供的代码详情中包含抽象基类，请忽略，只介绍具体的实现类

## 【严重警告】禁止编造

11. 【绝对禁止】编造任何不存在于"代码详情"中的类名、方法名、参数或返回值
12. 【绝对禁止】猜测或推断API签名，必须完全使用"代码详情"中提供的信息
13. 代码示例必须是用户可以直接运行的使用示例，不要展示如何继承或扩展

重要格式要求：
- 【禁止】在开头输出任何标题，标题会由系统自动添加
- 直接开始写内容

请输出内容：
"""

DEVELOPER_MANUAL_CONTENT_PROMPT = """你正在为项目 "{project_name}" 撰写开发者手册的 "{subsection_title}" 部分。

{context_info}

## 项目基本信息

{project_info}

## 写作要求（开发者手册）

1. 用中文撰写，语言简洁清晰，面向开发者
2. 内容要完整、准确、实用
3. 使用Markdown格式
4. 重点：接口定义、抽象方法、继承关系、扩展开发方法

## 【开发者手册特别要求】

5. 【重要】必须介绍所有类，包括抽象基类和具体实现类
6. 【重要】说明类的继承关系、基类定义、抽象方法
7. 【重要】提供接口签名、参数类型、返回值类型
8. 【重要】说明如何继承基类开发自定义实现
9. 如果是抽象类，必须明确标注，并说明需要实现的抽象方法

## 【严重警告】禁止编造

10. 【绝对禁止】编造任何不存在于"代码详情"中的类名、方法名、参数或返回值
11. 【绝对禁止】猜测或推断API签名，必须完全使用"代码详情"中提供的信息
12. 代码示例应展示如何扩展或实现，而非简单使用

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
    doc_type: DocType = "user_manual",
) -> str:
    if doc_type == "user_manual":
        template = USER_MANUAL_CONTENT_PROMPT
    elif doc_type == "developer_manual":
        template = DEVELOPER_MANUAL_CONTENT_PROMPT
    else:
        template = CONTENT_PROMPT_WITH_CONTEXT

    base_prompt = template.format(
        project_name=project_name,
        subsection_title=subsection_title,
        project_info=project_info,
        context_info=context_info,
    )

    if custom_style:
        base_prompt += f"\n\n用户自定义风格要求:\n{custom_style}"

    return base_prompt
