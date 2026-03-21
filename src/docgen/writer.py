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

        cleaned_content = self._clean_content(content)
        full_content = f"# {section_title}\n\n{cleaned_content}"
        file_path.write_text(full_content, encoding="utf-8")

        return str(file_path)

    def _clean_content(self, content: str) -> str:
        import re

        lines = content.strip().split("\n")
        cleaned_lines = []
        prev_title = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            if re.match(r"^#\s+[^#]", stripped):
                continue

            title_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if title_match:
                level = len(title_match.group(1))
                current_title = title_match.group(2).strip()

                if prev_title and current_title.lower() == prev_title.lower():
                    continue
                if level == 3 and prev_title and current_title in prev_title:
                    continue

                prev_title = current_title
            else:
                prev_title = None

            cleaned_lines.append(line)

        result = "\n".join(cleaned_lines).strip()
        result = re.sub(r"\n{3,}", "\n\n", result)

        return result

    def write_index(self, chapters: list[tuple[int, str, list[str]]]) -> str:
        content = f"""# {self.project_name} 文档

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## 目录

"""
        for chapter_idx, chapter_title, subsections in chapters:
            filename = f"{chapter_idx:02d}-{self._slugify(chapter_title)}.md"
            content += f"{chapter_idx}. [{chapter_title}]({filename})\n"
            for sub_idx, sub_title in enumerate(subsections, 1):
                anchor = self._anchor(sub_title)
                content += (
                    f"   {chapter_idx}.{sub_idx} [{sub_title}]({filename}#{anchor})\n"
                )

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
