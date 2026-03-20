# DocGen

交互式文档生成工具 - 自动分析代码项目并生成完整的中文用户文档。

## 特性

- **智能大纲生成** - LLM 自动分析项目结构，生成详细的文档大纲
- **完整API提取** - 使用 AST 分析代码，提取函数签名、参数、返回值、docstring
- **多章节生成** - 每个子章节独立调用 LLM，确保内容完整详细
- **Mermaid 图表** - 自动生成架构图、数据流图
- **支持多种项目** - Python、JavaScript、TypeScript 等

## 安装

```bash
pip install -e .
```

## 快速开始

```bash
# 创建配置文件
cp config.yaml.example config.yaml

# 编辑配置文件，设置你的 LLM API
# llm.api_base: OpenAI 兼容 API 地址
# llm.api_key: API 密钥
# llm.model: 模型名称

# 运行
docgen ./your-project -y
```

## 配置说明

```yaml
llm:
  api_base: "https://api.openai.com/v1"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-4o"
  temperature: 0.7
  max_tokens: 4096

output:
  path: "./docs"
  language: "zh-CN"

scan:
  exclude:
    - "node_modules"
    - ".git"
    - "__pycache__"
```

## CLI 选项

```
docgen [OPTIONS] PROJECT_PATH

选项:
  -c, --config PATH    配置文件路径
  -o, --output PATH    输出目录
  -y, --yes            跳过交互确认
  -v, --version        显示版本
  --help               显示帮助
```

## 输出结构

```
docs/
├── index.md           # 目录索引
├── 01-项目简介.md
├── 02-架构设计.md      # 含 Mermaid 图
├── 03-安装指南.md
├── 04-快速开始.md
├── 05-核心API.md      # 完整 API 文档
├── 06-连接器.md
├── 07-转换器.md
├── ...
└── NN-开发指南.md
```

## 工作原理

1. **扫描项目** - 读取目录结构、README、配置文件、依赖信息
2. **生成大纲** - LLM 分析项目后生成详细的文档大纲
3. **提取API信息** - 使用 AST 提取类、函数、参数等元信息
4. **分章节生成** - 每个子章节调用 LLM 生成详细内容
5. **输出文档** - 生成多文件 Markdown 文档

## LLM 调用次数

- 大纲生成: 1 次
- 子章节生成: N 次（取决于子章节数量）
- 总计: 约 50-60 次（对于中等规模项目）

## 许可证

MIT