"""
项目结构推断器 - 自动扫描项目，推断目录用途、模块关系

优先级：用户自定义规则 > 内置规则 > 内容推断
"""

import ast
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .config import Config, InferenceRulesConfig
from .scanner import Scanner


DEFAULT_DIRECTORY_TYPE_RULES = {
    "api": {"type": "entry", "description": "API入口"},
    "cli": {"type": "entry", "description": "命令行入口"},
    "main": {"type": "entry", "description": "主入口"},
    "ops": {"type": "core", "description": "核心算子模块"},
    "operators": {"type": "core", "description": "算子定义"},
    "pipeline": {"type": "core", "description": "Pipeline编排"},
    "core": {"type": "core", "description": "核心逻辑"},
    "mapper": {"type": "operators", "description": "映射算子，对数据进行变换处理"},
    "filter": {"type": "operators", "description": "过滤算子，筛选数据"},
    "connector": {"type": "operators", "description": "存储连接器，读写数据源"},
    "duplicator": {"type": "operators", "description": "去重算子"},
    "functions": {"type": "implementations", "description": "底层实现方法"},
    "utils": {"type": "implementations", "description": "工具函数"},
    "helpers": {"type": "implementations", "description": "辅助函数"},
    "tests": {"type": "tests", "description": "测试代码"},
    "docs": {"type": "docs", "description": "文档"},
    "examples": {"type": "examples", "description": "示例代码"},
    "models": {"type": "models", "description": "数据模型"},
    "schemas": {"type": "schemas", "description": "数据结构定义"},
    "services": {"type": "services", "description": "服务层"},
    "handlers": {"type": "handlers", "description": "请求处理"},
}


@dataclass
class ModuleRelation:
    source: str
    target: str
    relation_type: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DirectoryInfo:
    path: str
    type: str = "unknown"
    description: str = ""
    children: dict = field(default_factory=dict)
    key_files: list = field(default_factory=list)
    key_classes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "type": self.type,
            "description": self.description,
        }
        if self.children:
            result["children"] = {k: v.to_dict() for k, v in self.children.items()}
        if self.key_files:
            result["key_files"] = self.key_files
        if self.key_classes:
            result["key_classes"] = self.key_classes
        return result


@dataclass
class ProjectStructure:
    name: str
    type: str = "unknown"
    structure: dict = field(default_factory=dict)
    relations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project": {
                "name": self.name,
                "type": self.type,
            },
            "structure": {k: v.to_dict() for k, v in self.structure.items()},
            "relations": [r.to_dict() for r in self.relations],
        }

    def to_yaml(self) -> str:
        import yaml

        return yaml.dump(self.to_dict(), allow_unicode=True, default_flow_style=False)


class StructureInferrer:
    def __init__(self, scanner: Scanner, config: Config):
        self.scanner = scanner
        self.project_path = scanner.project_path
        self.config = config
        self.custom_rules = config.inference_rules

        self._files_info: dict = {}
        self._class_to_module: dict = {}
        self._dir_info_cache: dict = {}

    def scan_all_files(self) -> dict:
        if self._files_info:
            return self._files_info

        for py_file in self.project_path.rglob("*.py"):
            if self.scanner._should_exclude(py_file):
                continue

            relative_path = str(py_file.relative_to(self.project_path))
            file_info = self._analyze_file(py_file, relative_path)
            self._files_info[relative_path] = file_info

            for cls in file_info.get("classes", []):
                self._class_to_module[cls["name"]] = relative_path

        return self._files_info

    def _analyze_file(self, file_path: Path, relative_path: str) -> dict:
        file_info = {
            "path": relative_path,
            "classes": [],
            "functions": [],
            "imports": [],
            "docstring": "",
            "lines": 0,
        }

        try:
            content = file_path.read_text(encoding="utf-8")
            file_info["lines"] = len(content.splitlines())
            tree = ast.parse(content)

            if (
                tree.body
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
            ):
                file_info["docstring"] = tree.body[0].value.value or ""

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        file_info["imports"].append(node.module)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            file_info["imports"].append(alias.name)

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    class_info = self._extract_class(node)
                    file_info["classes"].append(class_info)
                elif isinstance(node, ast.FunctionDef):
                    func_info = self._extract_function(node)
                    file_info["functions"].append(func_info)

        except Exception as e:
            pass

        return file_info

    def _extract_class(self, node: ast.ClassDef) -> dict:
        class_info = {
            "name": node.name,
            "docstring": "",
            "bases": [],
            "methods": [],
        }

        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        ):
            class_info["docstring"] = node.body[0].value.value or ""

        for base in node.bases:
            if isinstance(base, ast.Name):
                class_info["bases"].append(base.id)
            elif isinstance(base, ast.Attribute):
                class_info["bases"].append(ast.unparse(base))

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                class_info["methods"].append(item.name)

        return class_info

    def _extract_function(self, node: ast.FunctionDef) -> dict:
        func_info = {
            "name": node.name,
            "docstring": "",
        }

        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        ):
            func_info["docstring"] = node.body[0].value.value or ""

        return func_info

    def infer_directory_type(self, dir_name: str, content_hints: dict = None) -> dict:
        dir_lower = dir_name.lower()

        custom_types = self.custom_rules.directory_types or {}
        for pattern, info in custom_types.items():
            if pattern.lower() in dir_lower:
                return {
                    "type": info.get("type", "unknown"),
                    "description": info.get("description", ""),
                }

        for pattern, info in DEFAULT_DIRECTORY_TYPE_RULES.items():
            if pattern in dir_lower:
                return info.copy()

        if content_hints:
            if content_hints.get("class_count", 0) >= 3:
                return {"type": "core", "description": "核心功能模块"}
            if content_hints.get("has_base_class"):
                return {"type": "core", "description": "基础定义模块"}

        return {"type": "unknown", "description": ""}

    def infer_module_relations(self) -> list[ModuleRelation]:
        relations = []

        custom_relations = self.custom_rules.module_relations or []
        for rel in custom_relations:
            relations.append(
                ModuleRelation(
                    source=rel.get("source", ""),
                    target=rel.get("target", ""),
                    relation_type=rel.get("type", "call"),
                    detail=rel.get("detail", ""),
                )
            )

        if not self._class_to_module:
            self.scan_all_files()

        for module_path, file_info in self._files_info.items():
            for cls in file_info.get("classes", []):
                for base in cls.get("bases", []):
                    base_module = self._class_to_module.get(base)
                    if base_module and base_module != module_path:
                        rel = ModuleRelation(
                            source=module_path,
                            target=base_module,
                            relation_type="inherit",
                            detail=f"{cls['name']} -> {base}",
                        )
                        if not any(
                            r.source == rel.source and r.target == rel.target
                            for r in relations
                        ):
                            relations.append(rel)

        return relations

    def infer(self) -> ProjectStructure:
        self.scan_all_files()

        structure = self._build_structure_tree()
        relations = self.infer_module_relations()

        project_type = self.custom_rules.project_type or self._determine_project_type()

        return ProjectStructure(
            name=self.project_path.name,
            type=project_type,
            structure=structure,
            relations=relations,
        )

    def _build_structure_tree(self, max_depth: int = 4) -> dict:
        structure = {}

        root_dirs = []
        for item in self.project_path.iterdir():
            if item.is_dir() and not self.scanner._should_exclude(item):
                if not item.name.startswith(".") and not item.name.startswith("_"):
                    root_dirs.append(item)

        for root_dir in root_dirs:
            dir_info = self._build_directory_info(
                root_dir, depth=0, max_depth=max_depth
            )
            structure[root_dir.name] = dir_info

        return structure

    def _build_directory_info(
        self, dir_path: Path, depth: int = 0, max_depth: int = 4
    ) -> DirectoryInfo:
        relative_path = str(dir_path.relative_to(self.project_path))

        if relative_path in self._dir_info_cache:
            return self._dir_info_cache[relative_path]

        content_hints = self._get_directory_content_hints(dir_path)
        type_info = self.infer_directory_type(dir_path.name, content_hints)

        dir_info = DirectoryInfo(
            path=relative_path,
            type=type_info["type"],
            description=type_info["description"],
        )

        py_files = list(dir_path.glob("*.py"))
        for py_file in py_files[:5]:
            if not py_file.name.startswith("_"):
                rel_file = str(py_file.relative_to(self.project_path))
                file_info = self._files_info.get(rel_file, {})
                classes = file_info.get("classes", [])
                dir_info.key_files.append(
                    {
                        "path": py_file.name,
                        "classes": [c["name"] for c in classes[:3]],
                    }
                )
                dir_info.key_classes.extend([c["name"] for c in classes])

        if depth < max_depth:
            sub_dirs = []
            for item in dir_path.iterdir():
                if item.is_dir() and not self.scanner._should_exclude(item):
                    if not item.name.startswith(".") and not item.name.startswith("_"):
                        sub_dirs.append(item)

            for sub_dir in sub_dirs:
                sub_info = self._build_directory_info(sub_dir, depth + 1, max_depth)
                dir_info.children[sub_dir.name] = sub_info

        self._dir_info_cache[relative_path] = dir_info
        return dir_info

    def _get_directory_content_hints(self, dir_path: Path) -> dict:
        hints = {
            "file_count": 0,
            "class_count": 0,
            "has_base_class": False,
        }

        for py_file in dir_path.glob("*.py"):
            if self.scanner._should_exclude(py_file):
                continue

            hints["file_count"] += 1
            rel_path = str(py_file.relative_to(self.project_path))
            file_info = self._files_info.get(rel_path, {})
            hints["class_count"] += len(file_info.get("classes", []))

            for cls in file_info.get("classes", []):
                if cls.get("bases"):
                    hints["has_base_class"] = True
                    break

        return hints

    def _determine_project_type(self) -> str:
        structure = self._build_structure_tree()

        types_found = set()
        for dir_name, dir_info in structure.items():
            types_found.add(dir_info.type)
            for sub_name, sub_info in dir_info.children.items():
                types_found.add(sub_info.type)

        if "operators" in types_found or "core" in types_found:
            for dir_name in structure.keys():
                if "pipeline" in dir_name.lower():
                    return "operator_framework"
            return "operator_framework"

        if "api" in types_found:
            return "web_api"

        if "cli" in types_found:
            return "cli_tool"

        return "library"

    def format_structure_tree(
        self, structure: ProjectStructure, max_depth: int = 2
    ) -> str:
        lines = []

        def render_dir(
            name: str, info: DirectoryInfo, prefix: str = "", depth: int = 0
        ):
            if depth > max_depth:
                return

            type_label = f"[{info.type}]" if info.type != "unknown" else ""
            lines.append(f"{prefix}├── {name}/ {type_label}")

            new_prefix = prefix + "│   "

            for key_file in info.key_files[:3]:
                classes_str = ""
                if key_file.get("classes"):
                    classes_str = f" ({', '.join(key_file['classes'][:2])})"
                lines.append(f"{new_prefix}├── {key_file['path']}{classes_str}")

            for child_name, child_info in info.children.items():
                render_dir(child_name, child_info, new_prefix, depth + 1)

        for dir_name, dir_info in structure.structure.items():
            render_dir(dir_name, dir_info)

        return "\n".join(lines)

    def format_relations(self, relations: list[ModuleRelation]) -> str:
        lines = []
        for rel in relations:
            lines.append(f"- {rel.source} → {rel.target} ({rel.relation_type})")
            if rel.detail:
                lines.append(f"  {rel.detail}")
        return "\n".join(lines)
