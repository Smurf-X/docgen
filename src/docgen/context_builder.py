"""
章节上下文组装器 - 为每个章节组装精准的上下文信息

根据章节类型和项目结构描述，组装精准的输入信息给LLM
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .structure_inferrer import ProjectStructure, DirectoryInfo
from .analyzer import CodeAnalyzer


CHAPTER_CONTEXT_RULES = {
    "概述": {
        "structure_depth": 2,
        "need_relations": False,
        "need_code": False,
        "writing_hints": [
            "介绍项目背景和目的",
            "说明核心特性",
            "概述适用场景",
        ],
    },
    "安装与配置": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": False,
        "writing_hints": [
            "说明环境要求",
            "给出安装步骤",
            "提供配置示例",
        ],
    },
    "快速入门": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": True,
        "writing_hints": [
            "提供最简单的使用示例",
            "展示基本用法流程",
            "给出可运行的代码",
        ],
    },
    "Pipeline 使用指南": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "说明如何使用 PipelineBuilder",
            "提供 YAML 配置格式",
            "展示算子编排方法",
        ],
    },
    "内置算子使用": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "列出每个算子的参数",
            "提供使用示例",
            "说明返回值和注意事项",
            "只介绍具体实现类，不介绍抽象基类",
        ],
    },
    "使用示例": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": True,
        "writing_hints": [
            "提供完整的使用场景",
            "展示代码和配置",
            "解释关键步骤",
        ],
    },
    "常见问题": {
        "structure_depth": 0,
        "need_relations": False,
        "need_code": False,
        "writing_hints": [
            "列出常见问题",
            "提供解决方案",
        ],
    },
    "架构设计": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "说明整体架构",
            "解释模块职责",
            "展示类继承关系",
        ],
    },
    "核心接口定义": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "列出抽象基类和接口",
            "说明抽象方法",
            "展示继承关系",
        ],
    },
    "开发自定义算子": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "说明如何扩展基类",
            "提供开发示例",
            "解释关键步骤",
        ],
    },
    "注册机制": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": True,
        "writing_hints": [
            "说明 OperatorRegistry 使用",
            "展示算子注册方法",
            "提供配置扩展示例",
        ],
    },
    "API 参考": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "列出类和方法签名",
            "说明参数和返回值",
            "提供使用示例",
        ],
    },
    "扩展开发最佳实践": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": True,
        "writing_hints": [
            "说明代码规范",
            "提供测试指南",
            "解释贡献流程",
        ],
    },
    "项目简介": {
        "structure_depth": 2,
        "need_relations": False,
        "need_code": False,
        "writing_hints": [
            "介绍项目背景",
            "说明核心特性",
        ],
    },
    "安装指南": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": False,
        "writing_hints": [
            "说明环境要求",
            "给出安装步骤",
            "提供配置示例",
        ],
    },
    "快速开始": {
        "structure_depth": 1,
        "need_relations": False,
        "need_code": True,
        "writing_hints": [
            "提供最简单的使用示例",
            "展示基本用法流程",
            "给出可运行的代码",
        ],
    },
    "算子参考": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "列出每个算子的参数",
            "提供YAML配置示例",
            "说明返回值和注意事项",
        ],
    },
    "开发指南": {
        "structure_depth": 2,
        "need_relations": True,
        "need_code": True,
        "writing_hints": [
            "说明如何扩展新功能",
            "提供基类接口说明",
            "给出开发示例",
        ],
    },
}


@dataclass
class ChapterContext:
    chapter_title: str
    chapter_description: str = ""
    relevant_structure: str = ""
    module_relations: list = field(default_factory=list)
    code_info: dict = field(default_factory=dict)
    writing_hints: list = field(default_factory=list)

    def format_for_prompt(self) -> str:
        lines = []

        if self.relevant_structure:
            lines.append("## 项目结构")
            lines.append("")
            lines.append("```")
            lines.append(self.relevant_structure)
            lines.append("```")
            lines.append("")

        if self.module_relations:
            lines.append("## 模块关系")
            lines.append("")
            for rel in self.module_relations:
                lines.append(
                    f"- {rel['source']} → {rel['target']} ({rel['relation_type']})"
                )
                if rel.get("detail"):
                    lines.append(f"  {rel['detail']}")
            lines.append("")

        if self.code_info:
            lines.append("## 代码详情")
            lines.append("")
            lines.append(self._format_code_info(self.code_info))
            lines.append("")

        if self.writing_hints:
            lines.append("## 写作要求")
            lines.append("")
            for hint in self.writing_hints:
                lines.append(f"- {hint}")
            lines.append("")

        return "\n".join(lines)

    def _format_code_info(self, code_info: dict) -> str:
        lines = []

        if code_info.get("classes"):
            for cls in code_info["classes"][:5]:
                lines.append(f"### 类: {cls.get('name', 'Unknown')}")
                lines.append("")

                if cls.get("bases"):
                    lines.append(f"**继承自**: {', '.join(cls['bases'])}")
                    lines.append("")

                if cls.get("docstring"):
                    lines.append(cls["docstring"][:300])
                    lines.append("")

                if cls.get("methods"):
                    lines.append("**方法**:")
                    for method in cls["methods"][:8]:
                        method_str = f"- `{method['name']}"
                        if method.get("parameters"):
                            params = ", ".join(str(p) for p in method["parameters"][:5])
                            method_str += f"({params})"
                        else:
                            method_str += "()"
                        if method.get("return_type"):
                            method_str += f" -> {method['return_type']}"
                        method_str += "`"
                        lines.append(method_str)
                        if method.get("docstring"):
                            lines.append(f"  {method['docstring'][:100]}")
                    lines.append("")

        if code_info.get("api_summary"):
            lines.append(code_info["api_summary"][:2000])

        return "\n".join(lines)


class ContextBuilder:
    def __init__(self, project_structure: ProjectStructure, analyzer: CodeAnalyzer):
        self.project_structure = project_structure
        self.analyzer = analyzer

    def build(
        self,
        chapter_title: str,
        chapter_description: str = "",
        module_path: str = "",
        class_name: str = "",
    ) -> ChapterContext:
        rules = CHAPTER_CONTEXT_RULES.get(
            chapter_title,
            {
                "structure_depth": 1,
                "need_relations": False,
                "need_code": False,
                "writing_hints": [],
            },
        )

        relevant_dirs = self._find_relevant_dirs(chapter_title, module_path)

        structure = ""
        if rules.get("structure_depth", 0) > 0:
            structure = self._extract_structure_tree(
                relevant_dirs, depth=rules.get("structure_depth", 2)
            )

        relations = []
        if rules.get("need_relations"):
            relations = self._filter_relations(relevant_dirs)

        code_info = {}
        if rules.get("need_code"):
            code_info = self._extract_code_info(relevant_dirs, module_path, class_name)

        writing_hints = rules.get("writing_hints", [])

        return ChapterContext(
            chapter_title=chapter_title,
            chapter_description=chapter_description,
            relevant_structure=structure,
            module_relations=relations,
            code_info=code_info,
            writing_hints=writing_hints,
        )

    def _find_relevant_dirs(
        self, chapter_title: str, module_path: str = ""
    ) -> list[str]:
        if module_path:
            return [module_path]

        title_lower = chapter_title.lower()

        if "算子" in chapter_title:
            return ["ops", "operators"]
        if "connector" in title_lower or "连接" in chapter_title:
            return ["connector"]
        if "mapper" in title_lower or "映射" in chapter_title:
            return ["mapper", "functions"]
        if "api" in title_lower:
            return ["api"]
        if "pipeline" in title_lower:
            return ["api", "ops", "pipeline"]

        core_dirs = []
        for dir_name, dir_info in self.project_structure.structure.items():
            if dir_info.type in ("core", "entry"):
                core_dirs.append(dir_name)

        return core_dirs

    def _extract_structure_tree(self, relevant_dirs: list[str], depth: int = 2) -> str:
        lines = []

        def render_dir(
            name: str, info: DirectoryInfo, prefix: str = "", current_depth: int = 0
        ):
            if current_depth > depth:
                return

            type_label = f"[{info.type}]" if info.type != "unknown" else ""
            lines.append(f"{prefix}├── {name}/ {type_label}")

            new_prefix = prefix + "│   "

            for key_file in info.key_files[:3]:
                lines.append(f"{new_prefix}├── {key_file['path']}")

            for child_name, child_info in info.children.items():
                if current_depth < depth:
                    render_dir(child_name, child_info, new_prefix, current_depth + 1)

        for dir_name, dir_info in self.project_structure.structure.items():
            if dir_name in relevant_dirs or not relevant_dirs:
                render_dir(dir_name, dir_info)

        return "\n".join(lines)

    def _filter_relations(self, relevant_dirs: list[str]) -> list[dict]:
        relations = []
        for rel in self.project_structure.relations:
            source_dir = rel.source.split("/")[0] if "/" in rel.source else rel.source
            target_dir = rel.target.split("/")[0] if "/" in rel.target else rel.target

            if source_dir in relevant_dirs or target_dir in relevant_dirs:
                relations.append(rel.to_dict())

        return relations[:10]

    def _extract_code_info(
        self, relevant_dirs: list[str], module_path: str = "", class_name: str = ""
    ) -> dict:
        code_info = {
            "classes": [],
            "api_summary": "",
        }

        if module_path:
            if class_name:
                info = self.analyzer.analyze_module(module_path)
                if info:
                    for cls in info.classes:
                        if cls.name == class_name:
                            code_info["classes"].append(self._format_class_info(cls))
                            break
                return code_info

            module_info = self.analyzer.get_api_summary([module_path])
            code_info["api_summary"] = module_info
            all_classes = self.analyzer.get_all_classes([module_path])
            for path, name, cls in all_classes[:3]:
                code_info["classes"].append(self._format_class_info(cls))
            return code_info

        for dir_name in relevant_dirs[:2]:
            actual_path = self._find_actual_dir(dir_name)
            if actual_path and actual_path.exists():
                py_files = [
                    f for f in actual_path.rglob("*.py") if not f.name.startswith("__")
                ][:5]
                module_paths = [
                    str(
                        f.relative_to(self.analyzer.project_path).with_suffix("")
                    ).replace(os.sep, ".")
                    for f in py_files
                ]
                all_classes = self.analyzer.get_all_classes(module_paths)
                for path, name, cls in all_classes[:5]:
                    code_info["classes"].append(self._format_class_info(cls))

        return code_info

    def _find_actual_dir(self, dir_name: str) -> Optional[Path]:
        actual_path = self.analyzer.project_path / dir_name
        if actual_path.exists():
            return actual_path

        for root_dir in self.project_structure.structure.keys():
            actual_path = self.analyzer.project_path / root_dir / dir_name
            if actual_path.exists():
                return actual_path

        return None

    def _format_class_info(self, cls) -> dict:
        return {
            "name": cls.name,
            "bases": cls.bases if hasattr(cls, "bases") else [],
            "docstring": cls.docstring if hasattr(cls, "docstring") else "",
            "methods": [
                {
                    "name": m.name,
                    "parameters": [str(p) for p in m.parameters]
                    if hasattr(m, "parameters")
                    else [],
                    "return_type": m.return_type if hasattr(m, "return_type") else "",
                    "docstring": m.docstring if hasattr(m, "docstring") else "",
                }
                for m in (cls.methods if hasattr(cls, "methods") else [])
            ],
        }
