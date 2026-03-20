import os
from pathlib import Path
from datetime import datetime
from typing import Optional


class Writer:
    def __init__(self, output_path: str, project_name: str):
        self.output_path = Path(output_path)
        self.project_name = project_name
        self.output_path.mkdir(parents=True, exist_ok=True)

    def write_section(
        self, section_index: int, section_title: str, content: str
    ) -> str:
        filename = f"{section_index:02d}-{self._slugify(section_title)}.md"
        file_path = self.output_path / filename

        full_content = f"# {section_title}\n\n{content}"
        file_path.write_text(full_content, encoding="utf-8")

        return str(file_path)

    def write_index(self, sections: list[tuple[int, str, list[str]]]) -> str:
        content = f"""# {self.project_name} 文档

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## 目录

"""
        for section_index, section_title, subsections in sections:
            filename = f"{section_index:02d}-{self._slugify(section_title)}.md"
            content += f"{section_index}. [{section_title}]({filename})\n"
            for i, sub_title in enumerate(subsections, 1):
                content += f"   {section_index}.{i} [{sub_title}]({filename}#{self._anchor(sub_title)})\n"

        index_path = self.output_path / "index.md"
        index_path.write_text(content, encoding="utf-8")
        return str(index_path)

    def _slugify(self, text: str) -> str:
        import re

        slug = ""
        for char in text:
            if char.isalnum() or char in ["-", "_"]:
                slug += char
            elif "\u4e00" <= char <= "\u9fff":
                slug += char
            else:
                slug += "-"

        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")

        return slug[:30] if len(slug) > 30 else slug

    def _anchor(self, text: str) -> str:
        import re

        anchor = text.lower()
        anchor = re.sub(r"[^\w\u4e00-\u9fff-]", "-", anchor)
        anchor = re.sub(r"-+", "-", anchor)
        return anchor.strip("-")

    def get_output_dir(self) -> str:
        return str(self.output_path)
