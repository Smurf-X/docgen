import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class ProjectInfo:
    path: str
    name: str
    language: str
    structure: str
    readme: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    core_modules: list[str] = field(default_factory=list)
    file_count: int = 0
    total_lines: int = 0

    def to_summary(self) -> str:
        parts = [
            f"项目名称: {self.name}",
            f"语言: {self.language}",
            f"文件数: {self.file_count}",
            f"代码行数: {self.total_lines}",
        ]

        if self.readme:
            readme_preview = (
                self.readme[:2000] if len(self.readme) > 2000 else self.readme
            )
            parts.append(f"\nREADME摘要:\n{readme_preview}")

        if self.dependencies:
            parts.append(f"\n主要依赖: {', '.join(self.dependencies[:20])}")

        if self.entry_points:
            parts.append(f"\n入口文件: {', '.join(self.entry_points[:5])}")

        parts.append(f"\n目录结构:\n{self.structure}")

        return "\n".join(parts)


class Scanner:
    LANGUAGE_MAP = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".java": "Java",
        ".rs": "Rust",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".swift": "Swift",
        ".kt": "Kotlin",
    }

    CONFIG_FILES = [
        "pyproject.toml",
        "setup.py",
        "requirements.txt",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "Gemfile",
        "composer.json",
    ]

    README_FILES = ["README.md", "README.rst", "README.txt", "readme.md"]

    ENTRY_POINT_PATTERNS = [
        "main.py",
        "__main__.py",
        "app.py",
        "run.py",
        "server.py",
        "index.js",
        "index.ts",
        "app.js",
        "app.ts",
        "main.go",
        "main.rs",
        "Main.java",
    ]

    def __init__(self, project_path: str, exclude: Optional[list[str]] = None):
        self.project_path = Path(project_path).resolve()
        self.exclude = exclude or []
        self._language_counts: dict[str, int] = {}

    def scan(self) -> ProjectInfo:
        structure = self._get_directory_tree()
        readme = self._read_readme()
        dependencies = self._parse_dependencies()
        entry_points = self._find_entry_points()
        core_modules = self._identify_core_modules()
        file_count, total_lines = self._count_files_and_lines()

        return ProjectInfo(
            path=str(self.project_path),
            name=self.project_path.name,
            language=self._detect_primary_language(),
            structure=structure,
            readme=readme,
            dependencies=dependencies,
            entry_points=entry_points,
            core_modules=core_modules,
            file_count=file_count,
            total_lines=total_lines,
        )

    def _should_exclude(self, path: Path) -> bool:
        name = path.name
        for pattern in self.exclude:
            if pattern.startswith("*."):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
            elif pattern in str(path):
                return True
        return False

    def _get_directory_tree(self, max_depth: int = 4) -> str:
        lines = []

        def walk(path: Path, prefix: str = "", depth: int = 0):
            if depth > max_depth:
                return

            try:
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            except PermissionError:
                return

            dirs = [x for x in items if x.is_dir() and not self._should_exclude(x)]
            files = [x for x in items if x.is_file() and not self._should_exclude(x)]

            for i, d in enumerate(dirs[:15]):
                is_last = (i == len(dirs[:15]) - 1) and len(files) == 0
                lines.append(f"{prefix}{'└── ' if is_last else '├── '}{d.name}/")
                new_prefix = prefix + ("    " if is_last else "│   ")
                walk(d, new_prefix, depth + 1)

            if len(dirs) > 15:
                lines.append(f"{prefix}├── ... ({len(dirs) - 15} more directories)")

            for i, f in enumerate(files[:20]):
                is_last = i == len(files[:20]) - 1
                lines.append(f"{prefix}{'└── ' if is_last else '├── '}{f.name}")

            if len(files) > 20:
                lines.append(f"{prefix}└── ... ({len(files) - 20} more files)")

        lines.append(f"{self.project_path.name}/")
        walk(self.project_path, "")
        return "\n".join(lines)

    def _read_readme(self) -> Optional[str]:
        for readme_name in self.README_FILES:
            readme_path = self.project_path / readme_name
            if readme_path.exists():
                try:
                    return readme_path.read_text(encoding="utf-8")
                except:
                    pass
        return None

    def _parse_dependencies(self) -> list[str]:
        dependencies = []

        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8")
                import tomllib

                data = tomllib.loads(content)
                if "project" in data and "dependencies" in data["project"]:
                    dependencies.extend(data["project"]["dependencies"])
            except:
                pass

        requirements = self.project_path / "requirements.txt"
        if requirements.exists():
            try:
                content = requirements.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dependencies.append(
                            line.split("==")[0]
                            .split(">=")[0]
                            .split("<=")[0]
                            .split("[")[0]
                        )
            except:
                pass

        package_json = self.project_path / "package.json"
        if package_json.exists():
            try:
                content = package_json.read_text(encoding="utf-8")
                data = json.loads(content)
                deps = data.get("dependencies", {})
                dependencies.extend(list(deps.keys()))
            except:
                pass

        return list(set(dependencies))[:30]

    def _find_entry_points(self) -> list[str]:
        entry_points = []

        for pattern in self.ENTRY_POINT_PATTERNS:
            for match in self.project_path.rglob(pattern):
                if not self._should_exclude(match):
                    entry_points.append(str(match.relative_to(self.project_path)))

        return entry_points[:10]

    def _identify_core_modules(self) -> list[str]:
        modules = []

        src_dir = self.project_path / "src"
        lib_dir = self.project_path / "lib"

        for base_dir in [src_dir, lib_dir, self.project_path]:
            if base_dir.exists():
                for item in base_dir.iterdir():
                    if item.is_dir() and not self._should_exclude(item):
                        if not item.name.startswith(".") and not item.name.startswith(
                            "_"
                        ):
                            modules.append(item.name)
                    elif item.is_file() and item.suffix == ".py":
                        if not item.name.startswith("_"):
                            modules.append(item.stem)
                break

        return modules[:20]

    def _count_files_and_lines(self) -> tuple[int, int]:
        file_count = 0
        total_lines = 0

        for path in self.project_path.rglob("*"):
            if not path.is_file():
                continue
            if self._should_exclude(path):
                continue

            suffix = path.suffix.lower()
            if suffix in self.LANGUAGE_MAP:
                file_count += 1
                self._language_counts[self.LANGUAGE_MAP[suffix]] = (
                    self._language_counts.get(self.LANGUAGE_MAP[suffix], 0) + 1
                )
                try:
                    content = path.read_text(encoding="utf-8")
                    total_lines += len(content.splitlines())
                except:
                    pass

        return file_count, total_lines

    def _detect_primary_language(self) -> str:
        if not self._language_counts:
            return "Unknown"
        return max(self._language_counts.items(), key=lambda x: x[1])[0]

    def get_file_content(self, relative_path: str) -> Optional[str]:
        file_path = self.project_path / relative_path
        if file_path.exists() and file_path.is_file():
            try:
                return file_path.read_text(encoding="utf-8")
            except:
                pass
        return None

    def get_module_files(self, module_name: str, limit: int = 5) -> list[str]:
        files = []

        for pattern in [f"**/{module_name}/*.py", f"**/{module_name}.py"]:
            for match in self.project_path.rglob(pattern.replace("**/", "")):
                if not self._should_exclude(match):
                    files.append(str(match.relative_to(self.project_path)))
                    if len(files) >= limit:
                        return files

        return files
