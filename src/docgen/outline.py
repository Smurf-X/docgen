from dataclasses import dataclass, field
from typing import Optional


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
class Section:
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
    def from_dict(cls, data: dict) -> "Section":
        section = cls(
            title=data.get("title", ""), description=data.get("description", "")
        )
        for sub_data in data.get("subsections", []):
            section.subsections.append(SubSection.from_dict(sub_data))
        return section


@dataclass
class Outline:
    sections: list[Section] = field(default_factory=list)

    def to_dict(self):
        return {"sections": [s.to_dict() for s in self.sections]}

    @classmethod
    def from_dict(cls, data: dict) -> "Outline":
        outline = cls()
        for section_data in data.get("sections", []):
            outline.sections.append(Section.from_dict(section_data))
        return outline

    def display(self) -> str:
        lines = []
        for i, section in enumerate(self.sections, 1):
            lines.append(f"{i}. {section.title}")
            if section.description:
                lines.append(f"   描述: {section.description}")
            for j, sub in enumerate(section.subsections, 1):
                extra = (
                    f" ({sub.module_path}/{sub.class_name})"
                    if sub.module_path or sub.class_name
                    else ""
                )
                lines.append(f"   {i}.{j} {sub.title}{extra}")
        return "\n".join(lines)

    def count_subsections(self) -> int:
        total = 0
        for section in self.sections:
            total += len(section.subsections)
        return total

    def get_all_subsections(self) -> list[tuple[Section, SubSection]]:
        result = []
        for section in self.sections:
            for sub in section.subsections:
                result.append((section, sub))
        return result


OUTLINE_PROMPT = """你是一个技术文档专家。请根据以下项目信息，设计一份详细的用户文档大纲。

项目信息：
{project_info}

请按照以下结构生成大纲，每个章节可以有多个子章节。子章节可以指定对应的模块路径或类名，用于生成API文档。

输出JSON格式示例：
{{
  "sections": [
    {{
      "title": "项目简介",
      "description": "介绍项目背景和核心概念",
      "subsections": [
        {{"title": "项目背景", "description": "项目解决什么问题"}},
        {{"title": "核心概念", "description": "DocSet, Document等核心概念"}}
      ]
    }},
    {{
      "title": "架构设计",
      "description": "系统架构说明",
      "subsections": [
        {{"title": "整体架构", "description": "系统架构图和说明"}},
        {{"title": "数据流", "description": "数据处理流程"}}
      ]
    }},
    {{
      "title": "安装指南",
      "description": "安装和配置说明",
      "subsections": [
        {{"title": "环境要求", "description": "Python版本、依赖等"}},
        {{"title": "安装步骤", "description": "pip install等"}}
      ]
    }},
    {{
      "title": "快速开始",
      "description": "快速上手指南",
      "subsections": [
        {{"title": "Hello World", "description": "最简单的示例"}},
        {{"title": "基本流程", "description": "读取-处理-写入的基本流程"}}
      ]
    }},
    {{
      "title": "核心API",
      "description": "核心类和接口说明",
      "subsections": [
        {{"title": "Document类", "description": "文档对象", "module_path": "sycamore/document", "class_name": "Document"}},
        {{"title": "DocSet类", "description": "文档集合", "module_path": "sycamore/docset", "class_name": "DocSet"}}
      ]
    }},
    {{
      "title": "连接器",
      "description": "数据源连接器",
      "subsections": [
        {{"title": "文件连接器", "description": "文件读写", "module_path": "sycamore/connectors/file"}},
        {{"title": "Elasticsearch连接器", "description": "ES读写", "module_path": "sycamore/connectors/elasticsearch"}}
      ]
    }},
    {{
      "title": "转换器",
      "description": "数据处理转换器",
      "subsections": [
        {{"title": "文本提取", "description": "提取文本内容", "module_path": "sycamore/transforms/text_extraction"}},
        {{"title": "表格提取", "description": "提取表格数据", "module_path": "sycamore/transforms/extract_table"}}
      ]
    }},
    {{
      "title": "使用示例",
      "description": "完整的使用示例",
      "subsections": [
        {{"title": "PDF文档处理", "description": "处理PDF文件的完整示例"}},
        {{"title": "RAG应用", "description": "构建RAG应用的示例"}}
      ]
    }},
    {{
      "title": "开发指南",
      "description": "贡献代码指南",
      "subsections": [
        {{"title": "开发环境", "description": "搭建开发环境"}},
        {{"title": "贡献流程", "description": "如何贡献代码"}}
      ]
    }}
  ]
}}

请根据项目实际情况调整章节内容。确保：
1. 每个章节有明确的目标
2. 子章节划分合理，每个子章节应该足够具体
3. 对于API相关的子章节，尽量指定module_path和class_name
4. 大纲应该覆盖项目的所有重要功能

只输出JSON，不要有其他内容。
"""


SECTION_PROMPTS = {
    "项目简介": """请为以下项目生成"{subsection_title}"子章节的文档内容。

项目信息：
{project_info}

子章节描述：{subsection_description}

要求：
1. 用中文撰写，语言简洁清晰
2. 内容要完整、准确
3. 使用Markdown格式
4. 如果是"核心概念"部分，请用表格或列表清晰展示每个概念

直接输出Markdown内容，不要用代码块包裹：
""",
    "架构设计": """请为以下项目生成"{subsection_title}"子章节的文档内容。

项目信息：
{project_info}

模块信息：
{module_info}

子章节描述：{subsection_description}

要求：
1. 用中文撰写
2. 如果是整体架构，请生成Mermaid架构图
3. 如果是数据流，请说明数据处理流程
4. 内容要完整、准确
5. 使用Markdown格式

直接输出Markdown内容：
""",
    "安装指南": """请为以下项目生成"{subsection_title}"子章节的文档内容。

项目信息：
{project_info}

依赖信息：
{dependencies}

子章节描述：{subsection_description}

要求：
1. 用中文撰写
2. 给出具体的安装命令
3. 说明环境要求
4. 使用Markdown格式，命令用```bash包裹

直接输出Markdown内容：
""",
    "快速开始": """请为以下项目生成"{subsection_title}"子章节的文档内容。

项目信息：
{project_info}

示例代码：
{example_code}

子章节描述：{subsection_description}

要求：
1. 用中文撰写
2. 提供可运行的代码示例
3. 解释代码的每一步
4. 使用Markdown格式，代码用```python包裹

直接输出Markdown内容：
""",
    "核心API": """请为以下项目生成"{subsection_title}"的API文档。

项目信息：
{project_info}

API详细信息：
{api_info}

要求：
1. 用中文撰写
2. 包含类/函数的用途说明
3. 包含参数说明（参数名、类型、含义）
4. 包含返回值说明
5. 包含使用示例
6. 使用Markdown格式

直接输出Markdown内容：
""",
    "连接器": """请为以下项目生成"{subsection_title}"的文档。

项目信息：
{project_info}

连接器API信息：
{api_info}

要求：
1. 用中文撰写
2. 说明连接器的用途和适用场景
3. 给出初始化参数
4. 提供使用示例
5. 使用Markdown格式

直接输出Markdown内容：
""",
    "转换器": """请为以下项目生成"{subsection_title}"的文档。

项目信息：
{project_info}

转换器API信息：
{api_info}

要求：
1. 用中文撰写
2. 说明转换器的功能和用途
3. 给出参数说明
4. 提供使用示例
5. 使用Markdown格式

直接输出Markdown内容：
""",
    "使用示例": """请为以下项目生成"{subsection_title}"的完整示例文档。

项目信息：
{project_info}

相关API：
{api_info}

子章节描述：{subsection_description}

要求：
1. 用中文撰写
2. 提供完整的、可运行的代码示例
3. 详细解释代码的每个步骤
4. 包含预期输出或结果说明
5. 使用Markdown格式

直接输出Markdown内容：
""",
    "开发指南": """请为以下项目生成"{subsection_title}"子章节的文档内容。

项目信息：
{project_info}

子章节描述：{subsection_description}

要求：
1. 用中文撰写
2. 内容要完整、具体
3. 如果是开发环境搭建，给出具体步骤
4. 如果是贡献流程，说明具体流程
5. 使用Markdown格式

直接输出Markdown内容：
""",
}


def get_outline_prompt(project_info: str) -> str:
    return OUTLINE_PROMPT.format(project_info=project_info)


def get_section_prompt(
    section_title: str,
    subsection_title: str,
    subsection_description: str,
    project_info: str,
    module_info: str = "",
    api_info: str = "",
    example_code: str = "",
    dependencies: str = "",
) -> str:
    template = SECTION_PROMPTS.get(section_title, SECTION_PROMPTS["项目简介"])
    return template.format(
        subsection_title=subsection_title,
        subsection_description=subsection_description,
        project_info=project_info,
        module_info=module_info,
        api_info=api_info,
        example_code=example_code,
        dependencies=dependencies,
    )
