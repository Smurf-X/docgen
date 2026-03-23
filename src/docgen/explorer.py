"""
项目探索器 - 自动分析项目结构，生成项目全貌

分层探索流程：
1. 扫描文件结构
2. AST 提取代码结构
3. LLM 分析核心文件
4. 聚类汇总生成项目全貌
"""

import os
import json
import ast
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from collections import defaultdict

from openai import AsyncOpenAI

from .config import Config
from .scanner import Scanner


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    relative_path: str
    classes: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    docstring: str = ""
    lines: int = 0


@dataclass
class ClassInfo:
    """类信息"""
    name: str
    docstring: str = ""
    bases: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    init_params: list = field(default_factory=list)


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    docstring: str = ""
    params: list = field(default_factory=list)
    return_annotation: str = ""


@dataclass
class ModuleAnalysis:
    """模块分析结果"""
    path: str
    category: str = ""
    summary: str = ""
    is_core: bool = False
    input_types: list = field(default_factory=list)
    output_types: list = field(default_factory=list)
    use_case: str = ""
    classes: list = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ProjectOverview:
    """项目全貌"""
    name: str
    language: str
    project_type: str = ""
    summary: str = ""
    core_modules: list = field(default_factory=list)
    module_clusters: dict = field(default_factory=dict)
    data_flow: list = field(default_factory=list)
    key_classes: list = field(default_factory=list)


class Explorer:
    """项目探索器"""
    
    # 可能的核心模块名
    CORE_MODULE_PATTERNS = [
        "operators", "operator", "op",
        "pipelines", "pipeline",
        "core", "main", "app",
        "api", "server",
        "models", "model",
        "services", "service",
    ]
    
    # 可能的辅助模块名
    AUXILIARY_PATTERNS = [
        "utils", "util", "helpers", "helper",
        "common", "shared",
        "config", "settings",
        "tests", "test",
        "docs", "scripts",
    ]

    def __init__(self, config: Config, scanner: Scanner):
        self.config = config
        self.scanner = scanner
        self.project_path = scanner.project_path
        
        # 初始化 OpenAI 客户端
        self.client = AsyncOpenAI(
            base_url=config.llm.api_base,
            api_key=config.llm.api_key,
            timeout=config.llm.timeout,
            max_retries=config.llm.max_retries,
        )
        
        # 缓存
        self._files_info: dict[str, FileInfo] = {}
        self._module_analyses: dict[str, ModuleAnalysis] = {}

    def scan_all_files(self) -> dict[str, FileInfo]:
        """扫描所有 Python 文件并提取结构信息"""
        if self._files_info:
            return self._files_info
        
        for py_file in self.project_path.rglob("*.py"):
            # 检查是否应该排除
            if self.scanner._should_exclude(py_file):
                continue
            
            relative_path = str(py_file.relative_to(self.project_path))
            file_info = self._analyze_file(py_file, relative_path)
            self._files_info[relative_path] = file_info
        
        return self._files_info

    def _analyze_file(self, file_path: Path, relative_path: str) -> FileInfo:
        """分析单个文件"""
        file_info = FileInfo(
            path=str(file_path),
            relative_path=relative_path,
        )
        
        try:
            content = file_path.read_text(encoding="utf-8")
            file_info.lines = len(content.splitlines())
            
            # 解析 AST
            tree = ast.parse(content)
            
            # 提取模块级 docstring
            if (tree.body and 
                isinstance(tree.body[0], ast.Expr) and 
                isinstance(tree.body[0].value, ast.Constant)):
                file_info.docstring = tree.body[0].value.value or ""
            
            # 提取导入
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        file_info.imports.append(node.module)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            file_info.imports.append(alias.name)
            
            # 提取类和函数
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    class_info = self._extract_class(node)
                    file_info.classes.append(class_info)
                elif isinstance(node, ast.FunctionDef):
                    func_info = self._extract_function(node)
                    file_info.functions.append(func_info)
                    
        except Exception as e:
            print(f"分析文件失败 {relative_path}: {e}")
        
        return file_info

    def _extract_class(self, node: ast.ClassDef) -> ClassInfo:
        """提取类信息"""
        class_info = ClassInfo(name=node.name)
        
        # 提取 docstring
        if (node.body and 
            isinstance(node.body[0], ast.Expr) and 
            isinstance(node.body[0].value, ast.Constant)):
            class_info.docstring = node.body[0].value.value or ""
        
        # 提取基类
        for base in node.bases:
            if isinstance(base, ast.Name):
                class_info.bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                class_info.bases.append(ast.unparse(base))
        
        # 提取方法
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_info = self._extract_function(item)
                class_info.methods.append(method_info)
                
                # 提取 __init__ 参数
                if item.name == "__init__":
                    class_info.init_params = method_info.params
        
        return class_info

    def _extract_function(self, node: ast.FunctionDef) -> FunctionInfo:
        """提取函数信息"""
        func_info = FunctionInfo(name=node.name)
        
        # 提取 docstring
        if (node.body and 
            isinstance(node.body[0], ast.Expr) and 
            isinstance(node.body[0].value, ast.Constant)):
            func_info.docstring = node.body[0].value.value or ""
        
        # 提取参数
        for arg in node.args.args:
            param = {"name": arg.arg}
            if arg.annotation:
                param["type"] = ast.unparse(arg.annotation)
            func_info.params.append(param)
        
        # 提取默认值
        defaults = node.args.defaults
        if defaults:
            for i, default in enumerate(defaults):
                param_idx = len(func_info.params) - len(defaults) + i
                if param_idx >= 0:
                    func_info.params[param_idx]["default"] = ast.unparse(default)
        
        # 提取返回类型
        if node.returns:
            func_info.return_annotation = ast.unparse(node.returns)
        
        return func_info

    def get_directory_structure_summary(self) -> dict:
        """获取目录结构摘要"""
        self.scan_all_files()
        
        # 按目录分组
        dir_summary = defaultdict(lambda: {
            "file_count": 0,
            "total_lines": 0,
            "classes": [],
            "functions": [],
            "files": [],
        })
        
        for rel_path, file_info in self._files_info.items():
            # 获取目录路径
            parts = rel_path.split("/")
            if len(parts) > 1:
                dir_path = "/".join(parts[:-1])
            else:
                dir_path = "."
            
            dir_summary[dir_path]["file_count"] += 1
            dir_summary[dir_path]["total_lines"] += file_info.lines
            dir_summary[dir_path]["files"].append(rel_path)
            
            for cls in file_info.classes:
                dir_summary[dir_path]["classes"].append({
                    "name": cls.name,
                    "file": rel_path,
                    "docstring": cls.docstring[:100] if cls.docstring else "",
                })
        
        return dict(dir_summary)

    def identify_core_directories(self, dir_summary: dict) -> tuple[list[str], list[str]]:
        """识别核心目录和辅助目录"""
        core_dirs = []
        auxiliary_dirs = []
        
        for dir_path, info in dir_summary.items():
            dir_name = dir_path.split("/")[-1].lower()
            
            # 检查是否是核心模块
            is_core = False
            is_auxiliary = False
            
            for pattern in self.CORE_MODULE_PATTERNS:
                if pattern in dir_name:
                    is_core = True
                    break
            
            if not is_core:
                for pattern in self.AUXILIARY_PATTERNS:
                    if pattern in dir_name:
                        is_auxiliary = True
                        break
            
            # 基于内容判断
            if not is_core and not is_auxiliary:
                # 类数量多、代码行数多的可能是核心模块
                class_count = len(info["classes"])
                if class_count >= 3 and info["total_lines"] >= 100:
                    is_core = True
            
            if is_core:
                core_dirs.append(dir_path)
            elif is_auxiliary:
                auxiliary_dirs.append(dir_path)
        
        return core_dirs, auxiliary_dirs

    async def analyze_file_with_llm(self, file_info: FileInfo) -> ModuleAnalysis:
        """使用 LLM 分析单个文件"""
        
        # 构建分析内容
        content_parts = [f"文件: {file_info.relative_path}\n"]
        
        if file_info.docstring:
            content_parts.append(f"模块说明: {file_info.docstring[:200]}\n")
        
        if file_info.classes:
            content_parts.append("\n定义的类:")
            for cls in file_info.classes:
                content_parts.append(f"\n- {cls.name}")
                if cls.docstring:
                    content_parts.append(f": {cls.docstring[:100]}")
                if cls.bases:
                    content_parts.append(f" (继承: {', '.join(cls.bases)})")
                if cls.init_params:
                    params_str = ", ".join(
                        f"{p['name']}: {p.get('type', 'any')}" 
                        for p in cls.init_params[:5]
                    )
                    content_parts.append(f"\n  参数: {params_str}")
        
        if file_info.functions:
            content_parts.append("\n\n定义的函数:")
            for func in file_info.functions[:10]:  # 限制数量
                content_parts.append(f"\n- {func.name}")
                if func.return_annotation:
                    content_parts.append(f" -> {func.return_annotation}")
        
        content = "".join(content_parts)
        
        prompt = f"""分析以下代码文件并输出功能摘要。

{content}

请输出 JSON 格式（只输出 JSON，不要其他内容）:
{{
  "category": "功能类别（如 text_processing, image_processing, data_storage, pipeline, utils 等）",
  "summary": "一句话功能描述",
  "is_core": true或false（是否核心功能模块）,
  "input_types": ["输入数据类型列表"],
  "output_types": ["输出数据类型列表"],
  "use_case": "典型使用场景",
  "confidence": 0.0到1.0（分析置信度）
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 提取 JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            result = json.loads(result_text.strip())
            
            return ModuleAnalysis(
                path=file_info.relative_path,
                category=result.get("category", "unknown"),
                summary=result.get("summary", ""),
                is_core=result.get("is_core", False),
                input_types=result.get("input_types", []),
                output_types=result.get("output_types", []),
                use_case=result.get("use_case", ""),
                classes=[c.name for c in file_info.classes],
                confidence=result.get("confidence", 0.5),
            )
            
        except Exception as e:
            print(f"LLM 分析失败 {file_info.relative_path}: {e}")
            return ModuleAnalysis(
                path=file_info.relative_path,
                category="unknown",
                summary="",
                is_core=False,
                confidence=0.0,
            )

    async def analyze_directory_with_llm(self, dir_path: str, files_info: list[FileInfo]) -> ModuleAnalysis:
        """使用 LLM 分析整个目录"""
        
        # 构建目录摘要
        content_parts = [f"目录: {dir_path}\n"]
        content_parts.append(f"文件数: {len(files_info)}\n")
        
        all_classes = []
        for file_info in files_info:
            for cls in file_info.classes:
                all_classes.append({
                    "name": cls.name,
                    "file": file_info.relative_path,
                    "docstring": cls.docstring[:100] if cls.docstring else "",
                })
        
        if all_classes:
            content_parts.append("\n定义的类:")
            for cls in all_classes[:20]:  # 限制数量
                content_parts.append(f"\n- {cls['name']} ({cls['file']})")
                if cls["docstring"]:
                    content_parts.append(f": {cls['docstring']}")
        
        content = "".join(content_parts)
        
        prompt = f"""分析以下代码目录并输出功能摘要。

{content}

请输出 JSON 格式（只输出 JSON，不要其他内容）:
{{
  "category": "功能类别（如 text_processing, image_processing, data_storage, pipeline, utils 等）",
  "summary": "一句话功能描述",
  "is_core": true或false（是否核心功能模块）,
  "key_classes": ["核心类名列表"],
  "input_types": ["输入数据类型列表"],
  "output_types": ["输出数据类型列表"],
  "use_case": "典型使用场景"
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 提取 JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            result = json.loads(result_text.strip())
            
            return ModuleAnalysis(
                path=dir_path,
                category=result.get("category", "unknown"),
                summary=result.get("summary", ""),
                is_core=result.get("is_core", False),
                input_types=result.get("input_types", []),
                output_types=result.get("output_types", []),
                use_case=result.get("use_case", ""),
                classes=result.get("key_classes", []),
                confidence=0.8,
            )
            
        except Exception as e:
            print(f"LLM 分析目录失败 {dir_path}: {e}")
            return ModuleAnalysis(
                path=dir_path,
                category="unknown",
                summary="",
                is_core=False,
                confidence=0.0,
            )

    async def explore(self) -> ProjectOverview:
        """执行分层探索"""
        
        # 第 1 层：扫描所有文件
        print("第 1 层：扫描项目文件...")
        self.scan_all_files()
        dir_summary = self.get_directory_structure_summary()
        
        # 识别核心目录
        core_dirs, auxiliary_dirs = self.identify_core_directories(dir_summary)
        print(f"  发现 {len(self._files_info)} 个文件")
        print(f"  核心目录: {core_dirs}")
        print(f"  辅助目录: {auxiliary_dirs}")
        
        # 第 2 层：LLM 分析核心目录
        print("\n第 2 层：分析核心模块...")
        module_clusters = {}
        
        for dir_path in core_dirs:
            # 获取该目录下的所有文件
            dir_files_info = [
                self._files_info[f] 
                for f in dir_summary[dir_path]["files"] 
                if f in self._files_info
            ]
            
            if dir_files_info:
                print(f"  分析目录: {dir_path}")
                analysis = await self.analyze_directory_with_llm(dir_path, dir_files_info)
                module_clusters[dir_path] = analysis
                self._module_analyses[dir_path] = analysis
        
        # 对于辅助目录，只用规则判断，不调用 LLM
        for dir_path in auxiliary_dirs:
            analysis = ModuleAnalysis(
                path=dir_path,
                category="auxiliary",
                summary="辅助工具模块",
                is_core=False,
                confidence=0.5,
            )
            module_clusters[dir_path] = analysis
        
        # 第 3 层：生成项目全貌
        print("\n第 3 层：生成项目全貌...")
        overview = self._generate_overview(module_clusters)
        
        return overview

    def _generate_overview(self, module_clusters: dict) -> ProjectOverview:
        """生成项目全貌"""
        
        # 按重要性排序
        sorted_modules = sorted(
            module_clusters.items(),
            key=lambda x: (x[1].is_core, x[1].confidence),
            reverse=True
        )
        
        # 核心模块
        core_modules = [
            {
                "path": path,
                "category": analysis.category,
                "summary": analysis.summary,
                "classes": analysis.classes,
            }
            for path, analysis in sorted_modules
            if analysis.is_core
        ]
        
        # 关键类
        key_classes = []
        for path, analysis in sorted_modules:
            if analysis.is_core and analysis.classes:
                for cls in analysis.classes[:3]:
                    key_classes.append({
                        "name": cls,
                        "module": path,
                    })
        
        # 项目类型判断
        categories = [a.category for a in module_clusters.values()]
        project_type = self._determine_project_type(categories)
        
        # 生成摘要
        summary = self._generate_summary(module_clusters, project_type)
        
        return ProjectOverview(
            name=self.project_path.name,
            language=self.scanner._detect_primary_language(),
            project_type=project_type,
            summary=summary,
            core_modules=core_modules,
            module_clusters=module_clusters,
            key_classes=key_classes[:20],
        )

    def _determine_project_type(self, categories: list) -> str:
        """判断项目类型"""
        category_set = set(c.lower() for c in categories if c)
        
        if "text_processing" in category_set or "image_processing" in category_set:
            return "data_processing"
        if "pipeline" in category_set:
            return "etl_pipeline"
        if "api" in category_set:
            return "web_api"
        if "cli" in category_set:
            return "cli_tool"
        
        return "general"

    def _generate_summary(self, module_clusters: dict, project_type: str) -> str:
        """生成项目摘要"""
        core_summaries = [
            f"{path}: {analysis.summary}"
            for path, analysis in module_clusters.items()
            if analysis.is_core and analysis.summary
        ]
        
        if core_summaries:
            return f"这是一个{project_type}项目，核心功能包括：" + "；".join(core_summaries[:5])
        return f"这是一个{project_type}项目"

    def format_overview_for_prompt(self, overview: ProjectOverview) -> str:
        """将项目全貌格式化为 prompt 可用的文本"""
        lines = [
            f"# 项目全貌\n",
            f"项目名称: {overview.name}",
            f"语言: {overview.language}",
            f"类型: {overview.project_type}",
            f"",
            f"## 项目概述",
            overview.summary,
            f"",
            f"## 核心模块",
        ]
        
        for module in overview.core_modules:
            lines.append(f"")
            lines.append(f"### {module['path']}")
            lines.append(f"- 类别: {module['category']}")
            lines.append(f"- 功能: {module['summary']}")
            if module['classes']:
                lines.append(f"- 核心类: {', '.join(module['classes'][:10])}")
        
        if overview.key_classes:
            lines.append(f"")
            lines.append(f"## 关键类")
            for cls in overview.key_classes[:10]:
                lines.append(f"- {cls['name']} ({cls['module']})")
        
        return "\n".join(lines)

    # ========================================
    # 智能文件读取方法（模拟 ls/grep 命令）
    # ========================================

    def smart_ls(self, path: str = None, max_depth: int = 2) -> dict:
        """
        模拟 ls 命令，返回目录结构摘要
        只返回结构信息，不读取文件内容
        """
        target = Path(path) if path else self.project_path
        
        result = {
            "dirs": [],
            "files": [],
            "tree": "",
            "python_files": 0,
            "total_lines": 0,
        }
        
        lines = []
        
        def walk(current: Path, prefix: str = "", depth: int = 0):
            if depth > max_depth:
                return
            
            try:
                items = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            except PermissionError:
                return
            
            dirs = [x for x in items if x.is_dir() and not self.scanner._should_exclude(x)]
            files = [x for x in items if x.is_file() and not self.scanner._should_exclude(x)]
            
            for d in dirs[:20]:
                rel_dir = str(d.relative_to(self.project_path))
                result["dirs"].append(rel_dir)
                lines.append(f"{prefix}├── {d.name}/")
                walk(d, prefix + "│   ", depth + 1)
            
            if len(dirs) > 20:
                lines.append(f"{prefix}├── ... ({len(dirs) - 20} more dirs)")
            
            for f in files[:30]:
                rel_file = str(f.relative_to(self.project_path))
                result["files"].append(rel_file)
                if f.suffix == ".py":
                    result["python_files"] += 1
                lines.append(f"{prefix}├── {f.name}")
            
            if len(files) > 30:
                lines.append(f"{prefix}└── ... ({len(files) - 30} more files)")
        
        lines.append(f"{target.name}/")
        walk(target, "")
        result["tree"] = "\n".join(lines)
        
        return result

    def smart_read_head(self, file_path: str, lines: int = 50) -> str:
        """
        模拟 head 命令，只读取文件开头部分
        """
        try:
            full_path = self.project_path / file_path
            content = full_path.read_text(encoding="utf-8")
            return "\n".join(content.splitlines()[:lines])
        except Exception as e:
            return f"# 读取失败: {e}"

    def smart_grep_class(self, class_name: str, context_lines: int = 40) -> dict:
        """
        模拟 grep -A N，精准获取类定义
        只返回类定义部分，不返回整个文件
        """
        import re
        
        result = {
            "found": False,
            "file": "",
            "definition": "",
            "docstring": "",
            "methods": [],
            "init_params": [],
        }
        
        # 首先在已扫描的文件中查找
        for rel_path, file_info in self._files_info.items():
            for cls in file_info.classes:
                if cls.name == class_name:
                    result["found"] = True
                    result["file"] = rel_path
                    result["docstring"] = cls.docstring
                    result["methods"] = [{"name": m.name, "params": m.params, "return": m.return_annotation} for m in cls.methods]
                    result["init_params"] = cls.init_params
                    
                    # 读取完整的类定义代码
                    try:
                        full_path = self.project_path / rel_path
                        content = full_path.read_text(encoding="utf-8")
                        class_def = self._extract_class_code(content, class_name, context_lines)
                        result["definition"] = class_def
                    except:
                        pass
                    
                    return result
        
        return result

    def _extract_class_code(self, content: str, class_name: str, max_lines: int = 40) -> str:
        """
        从文件内容中提取类定义代码
        """
        import re
        
        lines = content.splitlines()
        pattern = rf"^(class\s+{re.escape(class_name)}\s*.*?):"
        
        for i, line in enumerate(lines):
            if re.match(pattern, line):
                # 找到类定义，提取到下一个顶级定义为止
                class_lines = [line]
                base_indent = len(line) - len(line.lstrip())
                
                for j in range(i + 1, min(i + max_lines + 1, len(lines))):
                    next_line = lines[j]
                    
                    # 空行继续
                    if not next_line.strip():
                        class_lines.append(next_line)
                        continue
                    
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    # 如果缩进回到类定义层级或更低，检查是否是新的顶级定义
                    if next_indent <= base_indent and next_line.strip():
                        # 检查是否是新的类或函数定义
                        if re.match(r"^(class |def |async def |@)", next_line):
                            break
                    
                    class_lines.append(next_line)
                
                return "\n".join(class_lines)
        
        return ""

    def smart_grep_function(self, func_name: str, context_lines: int = 20) -> dict:
        """
        模拟 grep -A N，精准获取函数定义
        """
        import re
        
        result = {
            "found": False,
            "file": "",
            "definition": "",
            "docstring": "",
            "params": [],
            "return_type": "",
        }
        
        # 在已扫描的文件中查找
        for rel_path, file_info in self._files_info.items():
            for func in file_info.functions:
                if func.name == func_name:
                    result["found"] = True
                    result["file"] = rel_path
                    result["docstring"] = func.docstring
                    result["params"] = func.params
                    result["return_type"] = func.return_annotation
                    
                    # 读取函数定义代码
                    try:
                        full_path = self.project_path / rel_path
                        content = full_path.read_text(encoding="utf-8")
                        func_def = self._extract_function_code(content, func_name, context_lines)
                        result["definition"] = func_def
                    except:
                        pass
                    
                    return result
            
            # 也检查类方法
            for cls in file_info.classes:
                for method in cls.methods:
                    if method.name == func_name:
                        result["found"] = True
                        result["file"] = rel_path
                        result["docstring"] = method.docstring
                        result["params"] = method.params
                        result["return_type"] = method.return_annotation
                        
                        try:
                            full_path = self.project_path / rel_path
                            content = full_path.read_text(encoding="utf-8")
                            func_def = self._extract_method_code(content, cls.name, func_name, context_lines)
                            result["definition"] = func_def
                        except:
                            pass
                        
                        return result
        
        return result

    def _extract_function_code(self, content: str, func_name: str, max_lines: int = 20) -> str:
        """从文件内容中提取函数定义代码"""
        import re
        
        lines = content.splitlines()
        pattern = rf"^(async\s+)?def\s+{re.escape(func_name)}\s*\("
        
        for i, line in enumerate(lines):
            if re.match(pattern, line):
                func_lines = [line]
                base_indent = len(line) - len(line.lstrip())
                
                for j in range(i + 1, min(i + max_lines + 1, len(lines))):
                    next_line = lines[j]
                    
                    if not next_line.strip():
                        func_lines.append(next_line)
                        continue
                    
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    if next_indent <= base_indent and next_line.strip():
                        if re.match(r"^(def |async def |class |@)", next_line):
                            break
                    
                    func_lines.append(next_line)
                
                return "\n".join(func_lines)
        
        return ""

    def _extract_method_code(self, content: str, class_name: str, method_name: str, max_lines: int = 20) -> str:
        """从文件内容中提取方法定义代码"""
        import re
        
        lines = content.splitlines()
        class_pattern = rf"^class\s+{re.escape(class_name)}\s*.*?:"
        method_pattern = rf"^\s+(async\s+)?def\s+{re.escape(method_name)}\s*\("
        
        in_class = False
        class_indent = 0
        
        for i, line in enumerate(lines):
            if re.match(class_pattern, line):
                in_class = True
                class_indent = len(line) - len(line.lstrip())
                continue
            
            if in_class and re.match(method_pattern, line):
                method_lines = [line]
                method_indent = len(line) - len(line.lstrip())
                
                for j in range(i + 1, min(i + max_lines + 1, len(lines))):
                    next_line = lines[j]
                    
                    if not next_line.strip():
                        method_lines.append(next_line)
                        continue
                    
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    if next_indent <= method_indent and next_line.strip():
                        break
                    
                    method_lines.append(next_line)
                
                return "\n".join(method_lines)
        
        return ""

    def smart_grep_usage(self, symbol_name: str, max_examples: int = 3) -> list:
        """
        搜索符号的使用示例
        优先搜索 tests/ 和 examples/ 目录
        """
        import re
        
        examples = []
        pattern = rf"\b{re.escape(symbol_name)}\b"
        
        # 优先搜索的目录
        search_dirs = ["tests", "test", "examples", "example", "docs"]
        
        for search_dir in search_dirs:
            dir_path = self.project_path / search_dir
            if not dir_path.exists():
                continue
            
            for py_file in dir_path.rglob("*.py"):
                if self.scanner._should_exclude(py_file):
                    continue
                
                try:
                    content = py_file.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    
                    for i, line in enumerate(lines):
                        if re.search(pattern, line):
                            # 提取上下文代码片段
                            start = max(0, i - 3)
                            end = min(len(lines), i + 10)
                            snippet = "\n".join(lines[start:end])
                            
                            examples.append({
                                "file": str(py_file.relative_to(self.project_path)),
                                "line": i + 1,
                                "snippet": snippet,
                            })
                            
                            if len(examples) >= max_examples:
                                return examples
                except:
                    pass
        
        return examples

    def smart_read_init(self, module_path: str) -> dict:
        """
        读取 __init__.py 获取模块导出的内容
        """
        import re
        
        result = {
            "exists": False,
            "exports": [],
            "imports": [],
        }
        
        init_file = self.project_path / module_path / "__init__.py"
        if not init_file.exists():
            return result
        
        result["exists"] = True
        
        try:
            content = init_file.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            for line in lines:
                line = line.strip()
                
                # 匹配 from xxx import yyy
                if match := re.match(r"from\s+\S+\s+import\s+(.+)", line):
                    items = match.group(1).replace("(", "").replace(")", "")
                    for item in items.split(","):
                        item = item.strip().split(" as ")[0]
                        if item and not item.startswith("*"):
                            result["exports"].append(item)
                
                # 匹配 import xxx
                elif match := re.match(r"import\s+(.+)", line):
                    items = match.group(1)
                    for item in items.split(","):
                        item = item.strip().split(" as ")[0]
                        if item:
                            result["imports"].append(item)
                
                # 匹配 __all__
                elif match := re.match(r"__all__\s*=\s*\[(.+)\]", line):
                    exports = re.findall(r"['\"](\w+)['\"]", match.group(1))
                    result["exports"].extend(exports)
        
        except Exception as e:
            pass
        
        return result

    def get_code_for_subsection(self, subsection_title: str, subsection_module: str = "", subsection_class: str = "") -> dict:
        """
        为文档子章节获取相关代码信息
        整合各种智能读取方法，返回精准的代码上下文
        """
        result = {
            "class_info": None,
            "function_info": None,
            "examples": [],
            "related_files": [],
        }
        
        # 1. 如果指定了类名，直接获取
        if subsection_class:
            class_info = self.smart_grep_class(subsection_class)
            if class_info["found"]:
                result["class_info"] = class_info
                # 查找使用示例
                result["examples"] = self.smart_grep_usage(subsection_class, max_examples=2)
                return result
        
        # 2. 如果指定了模块路径，获取模块信息
        if subsection_module:
            init_info = self.smart_read_init(subsection_module)
            if init_info["exports"]:
                # 获取第一个导出的类作为示例
                for export in init_info["exports"]:
                    if export[0].isupper():  # 假设是大写的类名
                        class_info = self.smart_grep_class(export)
                        if class_info["found"]:
                            result["class_info"] = class_info
                            break
        
        # 3. 根据标题关键词搜索相关类
        keywords = self._extract_keywords(subsection_title)
        for rel_path, file_info in self._files_info.items():
            for cls in file_info.classes:
                if self._matches_keywords(cls.name, keywords):
                    if result["class_info"] is None:
                        result["class_info"] = {
                            "found": True,
                            "file": rel_path,
                            "name": cls.name,
                            "docstring": cls.docstring,
                            "methods": [{"name": m.name} for m in cls.methods[:10]],
                            "init_params": cls.init_params,
                        }
                        result["examples"] = self.smart_grep_usage(cls.name, max_examples=2)
                        break
        
        return result

    def _extract_keywords(self, title: str) -> list:
        """从标题提取关键词"""
        # 常见的停用词
        stop_words = {"的", "和", "与", "或", "使用", "如何", "什么", "介绍", "说明", "指南", "文档"}
        
        words = title.replace("_", " ").replace("-", " ").split()
        keywords = []
        
        for word in words:
            word = word.lower()
            if len(word) > 2 and word not in stop_words:
                keywords.append(word)
        
        return keywords

    def _matches_keywords(self, text: str, keywords: list) -> bool:
        """检查文本是否匹配关键词"""
        if not keywords:
            return False
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def format_code_info_for_prompt(self, code_info: dict) -> str:
        """
        将代码信息格式化为 prompt 可用的文本
        控制在合理的 token 数量内
        """
        if not code_info.get("class_info"):
            return ""
        
        lines = []
        cls = code_info["class_info"]
        
        lines.append(f"### 相关代码")
        lines.append(f"类名: {cls.get('name', 'Unknown')}")
        lines.append(f"文件: {cls.get('file', '')}")
        
        if cls.get("docstring"):
            lines.append(f"说明: {cls['docstring'][:200]}")
        
        if cls.get("init_params"):
            lines.append("\n初始化参数:")
            for param in cls["init_params"][:5]:
                param_str = f"- {param['name']}"
                if param.get("type"):
                    param_str += f": {param['type']}"
                if param.get("default"):
                    param_str += f" = {param['default']}"
                lines.append(param_str)
        
        if cls.get("methods"):
            lines.append("\n主要方法:")
            for method in cls["methods"][:8]:
                lines.append(f"- {method.get('name', '')}")
        
        if code_info.get("examples"):
            lines.append("\n使用示例:")
            for example in code_info["examples"][:1]:
                lines.append(f"```python\n{example['snippet'][:500]}\n```")
        
        return "\n".join(lines)