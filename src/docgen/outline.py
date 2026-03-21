from dataclasses import dataclass, field
from typing import Optional


DEFAULT_CHAPTERS = [
    "项目简介",
    "架构设计",
    "安装指南",
    "快速开始",
    "API参考",
    "使用示例",
]


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
}


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
    chapter_title: str, project_info: str, extra_context: str = ""
) -> str:
    chapter_context = CHAPTER_PROMPTS.get(chapter_title, "")
    full_context = (
        f"{chapter_context}\n\n{extra_context}" if extra_context else chapter_context
    )
    return SUBSECTION_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        project_info=project_info,
        extra_context=full_context,
    )


def get_content_prompt(
    chapter_title: str,
    subsection_title: str,
    subsection_description: str,
    project_info: str,
    api_info: str = "",
) -> str:
    return CONTENT_PROMPT_TEMPLATE.format(
        subsection_title=subsection_title,
        subsection_description=subsection_description,
        chapter_title=chapter_title,
        project_info=project_info,
        api_info=api_info if api_info else "（无额外API信息）",
    )
