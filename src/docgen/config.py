import os
import re
from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class LLMConfig:
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 300.0      # 请求超时时间（秒）
    max_retries: int = 3        # 最大重试次数
    stream: bool = True         # 是否使用流式输出


@dataclass
class OutputConfig:
    path: str = "./docs"
    language: str = "zh-CN"


@dataclass
class ScanConfig:
    max_file_size: int = 100000
    exclude: list[str] = field(
        default_factory=lambda: [
            "node_modules",
            ".git",
            "__pycache__",
            "dist",
            "build",
            ".venv",
            "venv",
            "*.egg-info",
            ".tox",
            ".pytest_cache",
        ]
    )


@dataclass
class CustomizationConfig:
    """自定义文档风格配置"""
    style_guide: str = ""  # 风格指南文件路径
    extra_context: str = ""  # 额外上下文文件路径


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)
    customization: CustomizationConfig = field(default_factory=CustomizationConfig)

    @classmethod
    def load(cls, path: str) -> "Config":
        if not os.path.exists(path):
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data = cls._substitute_env_vars(data)
        return cls._from_dict(data)

    @staticmethod
    def _substitute_env_vars(data: dict) -> dict:
        def substitute(value):
            if isinstance(value, str):
                pattern = r"\$\{([^}]+)\}"

                def replacer(match):
                    return os.environ.get(match.group(1), match.group(0))

                return re.sub(pattern, replacer, value)
            elif isinstance(value, dict):
                return {k: substitute(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute(item) for item in value]
            return value

        return substitute(data)

    @classmethod
    def _from_dict(cls, data: dict) -> "Config":
        config = cls()

        if "llm" in data:
            config.llm = LLMConfig(
                **{
                    k: v
                    for k, v in data["llm"].items()
                    if k in LLMConfig.__dataclass_fields__
                }
            )

        if "output" in data:
            config.output = OutputConfig(
                **{
                    k: v
                    for k, v in data["output"].items()
                    if k in OutputConfig.__dataclass_fields__
                }
            )

        if "scan" in data:
            config.scan = ScanConfig(
                **{
                    k: v
                    for k, v in data["scan"].items()
                    if k in ScanConfig.__dataclass_fields__
                }
            )

        if "customization" in data:
            config.customization = CustomizationConfig(
                **{
                    k: v
                    for k, v in data["customization"].items()
                    if k in CustomizationConfig.__dataclass_fields__
                }
            )

        return config

    def load_customization_content(self, base_dir: str = ".") -> tuple[str, str]:
        """加载自定义风格指南和额外上下文内容
        
        Args:
            base_dir: 配置文件所在目录，用于解析相对路径
            
        Returns:
            (style_guide_content, extra_context_content)
        """
        style_content = ""
        extra_content = ""

        base_path = os.path.dirname(os.path.abspath(base_dir)) if base_dir else "."

        if self.customization.style_guide:
            style_path = self.customization.style_guide
            if not os.path.isabs(style_path):
                style_path = os.path.join(base_path, style_path)
            if os.path.exists(style_path):
                try:
                    with open(style_path, "r", encoding="utf-8") as f:
                        style_content = f.read()
                except Exception:
                    pass

        if self.customization.extra_context:
            extra_path = self.customization.extra_context
            if not os.path.isabs(extra_path):
                extra_path = os.path.join(base_path, extra_path)
            if os.path.exists(extra_path):
                try:
                    with open(extra_path, "r", encoding="utf-8") as f:
                        extra_content = f.read()
                except Exception:
                    pass

        return style_content, extra_content
