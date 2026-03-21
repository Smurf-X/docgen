import ast
import re
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class OpParameter:
    name: str
    type_hint: str = ""
    default: str = ""
    description: str = ""

    def to_markdown_row(self) -> str:
        default_val = self.default if self.default else "-"
        return f"| {self.name} | {self.type_hint or '-'} | {default_val} | {self.description or '-'} |"


@dataclass
class OperatorInfo:
    name: str
    category: str
    module_path: str
    description: str = ""
    parameters: list[OpParameter] = field(default_factory=list)
    example: str = ""
    returns: str = ""
    notes: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"### {self.name}", ""]

        if self.description:
            lines.append(f"**功能**：{self.description}")
            lines.append("")

        if self.parameters:
            lines.append("**参数**：")
            lines.append("")
            lines.append("| 参数名 | 类型 | 默认值 | 说明 |")
            lines.append("|--------|------|--------|------|")
            for p in self.parameters:
                lines.append(p.to_markdown_row())
            lines.append("")

        if self.example:
            lines.append("**配置示例**：")
            lines.append("")
            lines.append("```yaml")
            lines.append(self.example)
            lines.append("```")
            lines.append("")

        if self.returns:
            lines.append(f"**返回值**：{self.returns}")
            lines.append("")

        if self.notes:
            lines.append("**注意事项**：")
            for note in self.notes:
                lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class OpCategory:
    name: str
    description: str = ""
    operators: list[OperatorInfo] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"## {self.name}", ""]

        if self.description:
            lines.append(self.description)
            lines.append("")

        op_names = [
            f"[{op.name}](#{op.name.lower().replace('_', '-')})"
            for op in self.operators
        ]
        lines.append(f"**包含算子**：{', '.join(op_names)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for op in self.operators:
            lines.append(op.to_markdown())

        return "\n".join(lines)


class OperatorAnalyzer:
    COMMON_OP_DIRS = [
        "ops",
        "operators",
        "operations",
        "transforms",
        "processors",
        "filters",
        "mappers",
    ]

    OP_TYPE_PATTERNS = {
        "filter": ["filter", "Filter"],
        "mapper": ["mapper", "Mapper"],
        "deduplicator": ["dedup", "deduplicator", "Deduplicator"],
        "aggregator": ["aggregator", "Aggregator"],
        "selector": ["selector", "Selector"],
        "grouper": ["grouper", "Grouper"],
        "loader": ["loader", "reader", "Loader", "Reader"],
        "writer": ["writer", "Writer"],
    }

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self._op_dirs: list[Path] = []

    def scan_operators(self) -> list[OpCategory]:
        self._find_op_directories()

        categories_dict: dict[str, OpCategory] = {}

        for op_dir in self._op_dirs:
            category_name = op_dir.name
            if category_name not in categories_dict:
                categories_dict[category_name] = OpCategory(
                    name=self._format_category_name(category_name),
                    description=self._get_category_description(category_name),
                )

            for py_file in op_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                op_info = self._analyze_operator_file(py_file, category_name)
                if op_info:
                    categories_dict[category_name].operators.append(op_info)

        return list(categories_dict.values())

    def _find_op_directories(self):
        self._op_dirs = []

        for op_dir_name in self.COMMON_OP_DIRS:
            for match in self.project_path.rglob(op_dir_name):
                if match.is_dir() and not self._should_exclude(match):
                    self._op_dirs.append(match)

        sub_dirs = set()
        for op_dir in self._op_dirs[:]:
            for sub in op_dir.iterdir():
                if sub.is_dir() and not sub.name.startswith("_"):
                    sub_dirs.add(sub)

        self._op_dirs.extend(sub_dirs)
        self._op_dirs = list(set(self._op_dirs))

    def _should_exclude(self, path: Path) -> bool:
        exclude_patterns = ["test", "tests", "__pycache__", ".git", "node_modules"]
        for pattern in exclude_patterns:
            if pattern in str(path):
                return True
        return False

    def _analyze_operator_file(
        self, file_path: Path, category: str
    ) -> Optional[OperatorInfo]:
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except:
            return None

        op_info = None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if self._is_operator_class(node):
                    op_info = self._extract_op_info(node, file_path, category)
                    break

        return op_info

    def _is_operator_class(self, node: ast.ClassDef) -> bool:
        for base in node.bases:
            base_name = self._get_base_name(base)
            if any(
                op_type in base_name
                for op_types in self.OP_TYPE_PATTERNS.values()
                for op_type in op_types
            ):
                return True
            if base_name in [
                "Filter",
                "Mapper",
                "Deduplicator",
                "Aggregator",
                "Selector",
                "Grouper",
            ]:
                return True

        class_name = node.name.lower()
        for op_types in self.OP_TYPE_PATTERNS.values():
            if any(op_type.lower() in class_name for op_type in op_types):
                return True

        return False

    def _get_base_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _extract_op_info(
        self, node: ast.ClassDef, file_path: Path, category: str
    ) -> OperatorInfo:
        op_info = OperatorInfo(
            name=node.name,
            category=category,
            module_path=str(
                file_path.relative_to(self.project_path).with_suffix("")
            ).replace("\\", "/"),
            description="",
            parameters=[],
            example="",
        )

        docstring = ast.get_docstring(node)
        if docstring:
            op_info.description = self._extract_description(docstring)

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                op_info.parameters = self._extract_parameters(item)

        op_info.example = self._generate_example(op_info)

        return op_info

    def _extract_description(self, docstring: str) -> str:
        lines = docstring.strip().split("\n")
        desc_lines = []
        for line in lines:
            line = line.strip()
            if (
                line.startswith(":param")
                or line.startswith(":return")
                or line.startswith(":type")
            ):
                break
            if line:
                desc_lines.append(line)
        return " ".join(desc_lines)[:200]

    def _extract_parameters(self, init_node: ast.FunctionDef) -> list[OpParameter]:
        params = []

        docstring = ast.get_docstring(init_node) or ""
        param_docs = self._parse_param_docs(docstring)

        defaults_offset = len(init_node.args.args) - len(init_node.args.defaults)

        for i, arg in enumerate(init_node.args.args):
            if arg.arg in ["self", "cls", "args", "kwargs"]:
                continue

            param = OpParameter(
                name=arg.arg,
                type_hint=self._get_annotation(arg.annotation)
                if arg.annotation
                else "",
            )

            default_idx = i - defaults_offset
            if default_idx >= 0 and default_idx < len(init_node.args.defaults):
                param.default = self._get_default_value(
                    init_node.args.defaults[default_idx]
                )

            if arg.arg in param_docs:
                param.description = param_docs[arg.arg]

            params.append(param)

        return params

    def _parse_param_docs(self, docstring: str) -> dict[str, str]:
        docs = {}
        pattern = r":param\s+(\w+):\s*(.+?)(?=:param|:return|:type|$)"
        for match in re.finditer(pattern, docstring, re.DOTALL):
            param_name = match.group(1)
            param_desc = match.group(2).strip().replace("\n", " ")
            docs[param_name] = param_desc
        return docs

    def _get_annotation(self, node) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Subscript):
            return f"{self._get_annotation(node.value)}[{self._get_annotation(node.slice)}]"
        if isinstance(node, ast.Attribute):
            return f"{self._get_annotation(node.value)}.{node.attr}"
        return ""

    def _get_default_value(self, node) -> str:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return f'"{node.value}"'
            return str(node.value)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.List):
            return "[]"
        if isinstance(node, ast.Dict):
            return "{}"
        if isinstance(node, ast.Call):
            return f"{self._get_base_name(node.func)}()"
        return "..."

    def _generate_example(self, op_info: OperatorInfo) -> str:
        if not op_info.parameters:
            return f"{op_info.name}: {{}}"

        lines = [f"{op_info.name}:"]
        for p in op_info.parameters[:5]:
            default = p.default if p.default else '""'
            lines.append(f"  {p.name}: {default}")

        return "\n".join(lines)

    def _format_category_name(self, name: str) -> str:
        name_map = {
            "filter": "Filter 算子",
            "mapper": "Mapper 算子",
            "deduplicator": "Deduplicator 算子",
            "aggregator": "Aggregator 算子",
            "selector": "Selector 算子",
            "grouper": "Grouper 算子",
            "loader": "Loader 算子",
            "writer": "Writer 算子",
        }
        return name_map.get(name.lower(), f"{name.title()} 算子")

    def _get_category_description(self, name: str) -> str:
        desc_map = {
            "filter": "过滤算子用于根据条件筛选数据样本，保留符合条件的样本。",
            "mapper": "映射算子用于对数据样本进行变换处理，生成新的字段或修改现有内容。",
            "deduplicator": "去重算子用于识别和移除重复的数据样本。",
            "aggregator": "聚合算子用于将多个数据样本合并为一个样本。",
            "selector": "选择算子用于从数据样本中选择特定的字段或内容。",
            "grouper": "分组算子用于将数据样本按特定条件分组。",
        }
        return desc_map.get(name.lower(), "")

    def get_operator_count(self) -> dict[str, int]:
        categories = self.scan_operators()
        return {cat.name: len(cat.operators) for cat in categories}

    def has_operators(self) -> bool:
        self._find_op_directories()
        return len(self._op_dirs) > 0
