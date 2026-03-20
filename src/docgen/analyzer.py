import ast
import inspect
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ParameterInfo:
    name: str
    type_hint: str = ""
    default: str = ""

    def __str__(self):
        result = self.name
        if self.type_hint:
            result += f": {self.type_hint}"
        if self.default:
            result += f" = {self.default}"
        return result


@dataclass
class FunctionInfo:
    name: str
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    is_method: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False

    def to_markdown(self, indent: str = "") -> str:
        lines = []
        params_str = ", ".join(str(p) for p in self.parameters)
        signature = f"{self.name}({params_str})"
        if self.return_type:
            signature += f" -> {self.return_type}"

        lines.append(f"{indent}### `{signature}`")
        if self.docstring:
            lines.append(f"{indent}")
            for line in self.docstring.strip().split("\n"):
                lines.append(f"{indent}{line}")
        lines.append(f"{indent}")
        return "\n".join(lines)


@dataclass
class ClassInfo:
    name: str
    bases: list[str] = field(default_factory=list)
    docstring: str = ""
    methods: list[FunctionInfo] = field(default_factory=list)
    class_methods: list[FunctionInfo] = field(default_factory=list)
    static_methods: list[FunctionInfo] = field(default_factory=list)
    properties: list[FunctionInfo] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"## {self.name}"]

        if self.bases:
            lines.append(f"**继承自**: {', '.join(self.bases)}")
            lines.append("")

        if self.docstring:
            lines.append(self.docstring.strip())
            lines.append("")

        if self.methods:
            lines.append("### 方法")
            lines.append("")
            for method in self.methods:
                lines.append(method.to_markdown())

        if self.class_methods:
            lines.append("### 类方法")
            lines.append("")
            for method in self.class_methods:
                lines.append(method.to_markdown())

        if self.properties:
            lines.append("### 属性")
            lines.append("")
            for prop in self.properties:
                lines.append(prop.to_markdown())

        return "\n".join(lines)


@dataclass
class ModuleInfo:
    name: str
    path: str
    docstring: str = ""
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def to_summary(self) -> str:
        lines = [f"# 模块: {self.name}"]
        lines.append(f"路径: {self.path}")

        if self.docstring:
            lines.append("")
            lines.append(self.docstring.strip()[:500])

        if self.classes:
            lines.append("")
            lines.append("## 类")
            for cls in self.classes:
                desc = cls.docstring.split("\n")[0] if cls.docstring else "无描述"
                methods_count = len(cls.methods) + len(cls.class_methods)
                lines.append(f"- **{cls.name}**: {desc} ({methods_count}个方法)")

        if self.functions:
            lines.append("")
            lines.append("## 函数")
            for func in self.functions:
                desc = func.docstring.split("\n")[0] if func.docstring else "无描述"
                lines.append(f"- **{func.name}**: {desc}")

        return "\n".join(lines)


class CodeAnalyzer:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def analyze_file(self, file_path: str) -> Optional[ModuleInfo]:
        full_path = (
            self.project_path / file_path
            if not Path(file_path).is_absolute()
            else Path(file_path)
        )

        if not full_path.exists() or not str(full_path).endswith(".py"):
            return None

        try:
            source = full_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as e:
            return None

        module_info = ModuleInfo(
            name=full_path.stem,
            path=str(file_path),
            docstring=ast.get_docstring(tree) or "",
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_info.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    module_info.imports.append(
                        f"{module}.{alias.name}" if module else alias.name
                    )

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls_info = self._parse_class(node)
                module_info.classes.append(cls_info)
            elif isinstance(node, ast.FunctionDef) or isinstance(
                node, ast.AsyncFunctionDef
            ):
                func_info = self._parse_function(node)
                module_info.functions.append(func_info)

        return module_info

    def _parse_class(self, node: ast.ClassDef) -> ClassInfo:
        cls_info = ClassInfo(
            name=node.name,
            bases=[self._get_name(base) for base in node.bases],
            docstring=ast.get_docstring(node) or "",
        )

        for item in node.body:
            if isinstance(item, ast.FunctionDef) or isinstance(
                item, ast.AsyncFunctionDef
            ):
                func_info = self._parse_function(item, is_method=True)

                decorators = [self._get_name(d) for d in item.decorator_list]

                if "classmethod" in decorators:
                    func_info.is_classmethod = True
                    cls_info.class_methods.append(func_info)
                elif "staticmethod" in decorators:
                    func_info.is_staticmethod = True
                    cls_info.static_methods.append(func_info)
                elif "property" in decorators:
                    cls_info.properties.append(func_info)
                elif item.name.startswith("_") and not item.name.startswith("__"):
                    pass
                elif item.name.startswith("__") and item.name.endswith("__"):
                    if item.name in [
                        "__init__",
                        "__call__",
                        "__enter__",
                        "__exit__",
                        "__iter__",
                        "__next__",
                    ]:
                        cls_info.methods.append(func_info)
                else:
                    cls_info.methods.append(func_info)

        return cls_info

    def _parse_function(self, node, is_method: bool = False) -> FunctionInfo:
        func_info = FunctionInfo(
            name=node.name,
            return_type=self._get_annotation(node.returns) if node.returns else "",
            docstring=ast.get_docstring(node) or "",
            is_method=is_method,
        )

        params = []
        defaults_offset = len(node.args.args) - len(node.args.defaults)

        for i, arg in enumerate(node.args.args):
            if is_method and i == 0 and arg.arg == "self":
                continue
            if is_method and i == 0 and arg.arg == "cls":
                continue

            param = ParameterInfo(
                name=arg.arg,
                type_hint=self._get_annotation(arg.annotation)
                if arg.annotation
                else "",
            )

            default_idx = i - defaults_offset
            if default_idx >= 0 and default_idx < len(node.args.defaults):
                param.default = self._get_value(node.args.defaults[default_idx])

            params.append(param)

        if node.args.vararg:
            params.append(ParameterInfo(name=f"*{node.args.vararg.arg}"))

        for i, arg in enumerate(node.args.kwonlyargs):
            param = ParameterInfo(
                name=arg.arg,
                type_hint=self._get_annotation(arg.annotation)
                if arg.annotation
                else "",
            )
            if i < len(node.args.kw_defaults) and node.args.kw_defaults[i]:
                param.default = self._get_value(node.args.kw_defaults[i])
            params.append(param)

        if node.args.kwarg:
            params.append(ParameterInfo(name=f"**{node.args.kwarg.arg}"))

        func_info.parameters = params
        return func_info

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
        if isinstance(node, ast.Tuple):
            return ", ".join(self._get_annotation(el) for el in node.elts)
        return ""

    def _get_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        return ""

    def _get_value(self, node) -> str:
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        if isinstance(node, ast.List):
            return "[]"
        if isinstance(node, ast.Dict):
            return "{}"
        if isinstance(node, ast.Call):
            return f"{self._get_name(node.func)}(...)"
        return "..."

    def analyze_module(self, module_path: str) -> Optional[ModuleInfo]:
        module_dir = self.project_path / module_path

        if module_dir.is_file() and module_dir.suffix == ".py":
            return self.analyze_file(str(module_dir.relative_to(self.project_path)))

        if module_dir.is_dir():
            init_file = module_dir / "__init__.py"
            if init_file.exists():
                return self.analyze_file(str(init_file.relative_to(self.project_path)))

        return None

    def get_api_summary(self, module_paths: list[str]) -> str:
        summaries = []

        for module_path in module_paths:
            info = self.analyze_module(module_path)
            if info:
                summaries.append(info.to_summary())

        return "\n\n---\n\n".join(summaries)

    def get_class_details(self, module_path: str, class_name: str) -> Optional[str]:
        info = self.analyze_module(module_path)
        if not info:
            return None

        for cls in info.classes:
            if cls.name == class_name:
                return cls.to_markdown()

        return None

    def get_all_classes(
        self, module_paths: list[str]
    ) -> list[tuple[str, str, ClassInfo]]:
        result = []

        for module_path in module_paths:
            info = self.analyze_module(module_path)
            if info:
                for cls in info.classes:
                    result.append((module_path, info.name, cls))

        return result

    def get_all_functions(
        self, module_paths: list[str]
    ) -> list[tuple[str, str, FunctionInfo]]:
        result = []

        for module_path in module_paths:
            info = self.analyze_module(module_path)
            if info:
                for func in info.functions:
                    result.append((module_path, info.name, func))

        return result
