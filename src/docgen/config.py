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
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)

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

        return config
