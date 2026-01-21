# 医学 SCI 论文自动审稿系统

> Medical SCI Paper Automated Review System

A sophisticated AI-powered system for automated pre-review and screening of medical research manuscripts, based on international reporting guidelines (CONSORT, PRISMA, STROBE, etc.).

## 🎯 系统定位 (System Purpose)

本系统定位为医学学术期刊（特别是 SCI 收录期刊）的**"预审与辅助审稿（Pre-review）"**平台。核心任务是在稿件送交人类同行评议专家之前，进行自动化的、结构化的初步筛查。

**关键特性:**

- ✅ **辅助工具，非替代品**: 协助编辑和审稿人，不替代人类判断
- ✅ **Checklist 驱动**: 基于国际权威报告指南（CONSORT, PRISMA, STROBE, TRIPOD等）
- ✅ **证据可追溯**: 所有判断都提供原文引用和精确位置
- ✅ **高并发低延迟**: 优化的并发架构，单篇论文审稿时间 < 3分钟
- ✅ **无需微调**: 不依赖LLM微调，知识通过外部Checklist注入

## 🏗️ 系统架构

### 核心设计原则

1. **No Fine-tuning**: 避免知识幻觉和灾难性遗忘
2. **Checklist/Rubric Driven**: 严格遵循可量化的评估规则
3. **Evidence-based & Traceable**: 每个判断都有证据支撑
4. **High-Concurrency Design**: 最大化并发，最小化串行依赖

### Pipeline 流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     文档解析与清洗                                 │
│                   (Document Parsing)                             │
└──────────────────────┬──────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────────┐
│              结构化中间表示 + 研究类型识别                            │
│         (DocumentIR + Study Type Classification)                │
│          ⚡ 单次 LLM 调用完成所有任务                               │
└──────────────────────┬──────────────────────────────────────────┘
                       ↓
        ┌──────────────┴──────────────┐
        ↓                             ↓
┌───────────────────┐      ┌──────────────────────┐
│ 安全与伦理检查      │      │  Rubric 编排          │
│ (Integrity Guard) │      │  (Orchestrator)      │
└───────┬───────────┘      └──────────┬───────────┘
        │                             ↓
        │                  ┌──────────────────────┐
        │                  │  创建并发执行块         │
        │                  │  (Rubric Blocks)     │
        │                  └──────────┬───────────┘
        │                             ↓
        │              ┌──────────────┴──────────────┐
        │              ↓                             ↓
        │    ┌──────────────────┐         ┌──────────────────┐
        │    │ Methodology       │   ...   │ Statistician     │
        │    │ Reviewer 1        │         │ Reviewer         │
        │    └──────────┬────────┘         └────────┬─────────┘
        │               │                           │
        │               └───────────┬───────────────┘
        │                           ↓
        │               ┌──────────────────────────┐
        │               │   汇总所有并发结果          │
        └───────────────►  (All Results Collected)  │
                        └──────────┬───────────────┘
                                   ↓
                        ┌──────────────────────────┐
                        │   Editor Synthesizer     │
                        │   (Report Generation)    │
                        └──────────┬───────────────┘
                                   ↓
                ┌──────────────────┴──────────────────┐
                ↓                                     ↓
    ┌──────────────────────┐            ┌──────────────────────┐
    │   Author Report       │            │   Editor Report      │
    │   (详细修改建议)        │            │   (送审决策建议)       │
    └──────────────────────┘            └──────────────────────┘
```

## 📦 项目结构

```
.
├── src/
│   ├── agents/              # 各类审稿 Agent
│   │   ├── document_analyzer.py       # 文档结构化分析
│   │   ├── integrity_guard.py         # 安全与伦理检查
│   │   ├── rubric_orchestrator.py     # Rubric 编排
│   │   ├── methodology_reviewer.py    # 方法学审稿
│   │   ├── statistician_reviewer.py   # 统计学审稿
│   │   └── editor_synthesizer.py      # 报告合成
│   ├── schemas/             # 数据模式定义
│   │   ├── document_ir.py             # DocumentIR 结构
│   │   ├── rubric.py                  # Rubric 相关模式
│   │   ├── review_state.py            # 审稿状态
│   │   └── reports.py                 # 报告模式
│   ├── services/            # 核心服务
│   │   ├── llm_gateway.py             # LLM 统一调用接口
│   │   └── document_parser.py         # 文档解析
│   ├── rubrics/             # Checklist/Rubric 库
│   │   ├── universal_rubric.yaml      # 通用评估标准
│   │   ├── consort_2010.yaml          # CONSORT 2010
│   │   └── ...                        # 更多 Checklists
│   ├── utils/               # 工具函数
│   │   └── rubric_loader.py           # Rubric 加载器
│   └── main.py              # 主入口与编排
├── tests/                   # 测试文件
├── requirements.txt         # 依赖包
└── README.md               # 本文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

支持 OpenAI 或 Anthropic:

```bash
# 使用 OpenAI
export OPENAI_API_KEY="your-api-key-here"

# 或使用 Anthropic
export ANTHROPIC_API_KEY="your-api-key-here"
```

### 3. 运行审稿

```bash
# 命令行方式
python -m src.main /path/to/your/manuscript.pdf

# 或使用 Python 脚本
python
>>> from src.main import ReviewOrchestrator
>>> import asyncio
>>>
>>> orchestrator = ReviewOrchestrator(llm_api_key="your-key")
>>> review_state, author_report, editor_report = await orchestrator.review_manuscript("paper.pdf")
```

### 4. 查看结果

审稿完成后,会在 `review_output/` 目录生成两份报告:

- `{job_id}_author_report.md` - 面向作者的详细修改建议
- `{job_id}_editor_report.md` - 面向编辑的决策建议

## 📚 支持的研究类型与 Checklist

### 当前已实现

| 研究类型 | Checklist | 评估项数量 |
|---------|-----------|----------|
| 所有类型 | Universal Medical Manuscript Rubric | 12 |
| RCT | CONSORT 2010 | 25 |

### 计划扩展

- PRISMA 2020 (系统综述)
- STROBE (观察性研究)
- TRIPOD-AI (预测模型)
- STARD (诊断准确性研究)
- CARE (病例报告)
- 更多...

## 🎨 核心 Agent 说明

### 1. Document Analyzer Agent

**功能**: 将原始论文转化为结构化的 DocumentIR

**优化要点**:
- ⚡ **单次 LLM 调用** 完成: 章节划分 + 信息提取 + 研究类型识别
- 使用 Advanced 模型确保高质量输出
- 生成 EvidenceMap 加速下游检索

### 2. Integrity & Ethics Guard

**功能**: 安全检查和基础伦理合规

**检查内容**:
- Prompt Injection 攻击检测
- 隐藏/不可见文本检测
- 伦理批准声明检查

### 3. Rubric Orchestrator

**功能**: 动态加载和编排 Checklist

**工作流程**:
1. 根据研究类型加载适用的 Checklist
2. 将评估项划分为 5-8 个一组的 Block
3. 分配优先级（Critical > Major > Minor）

### 4. Methodology Reviewer Agent (并发)

**功能**: 执行具体的方法学评估

**特点**:
- 无状态，可大规模并发
- 每个 Agent 处理一个 Rubric Block
- 提供证据引用和精确位置

### 5. Statistician Reviewer Agent (并发)

**功能**: 专注统计学方法评估

**评估内容**:
- 样本量计算
- 统计检验选择
- 多重比较校正
- 模型验证方法

### 6. Editor Synthesizer Agent

**功能**: 汇总结果并生成最终报告

**处理步骤**:
1. 汇总所有并发 Agent 的结果
2. 去重和风险排序
3. 生成两份独立报告 (Author + Editor)
4. 使用 Advanced 模型确保报告质量

## ⚡ 性能优化策略

### 1. LLM 调用合并

- Document Analyzer: 5-10 次调用 → **1 次调用**
- 端到端总调用次数: 约 **17 次** (1 解析 + 15 并发审稿 + 1 合成)

### 2. 并发粒度设计

- **并发单元**: Rubric Block (5-8 个评估项)
- **避免过细**: 不是每个评估项一次调用
- **避免过粗**: 不是整个 Checklist 一次调用

### 3. 证据索引加速

- EvidenceMap 预先构建关键词索引
- Reviewer Agent 直接定位相关段落
- 避免重复的全文扫描

### 4. 模型分级使用

- **Advanced 模型**: Document Analyzer, Editor Synthesizer
- **Standard 模型**: Methodology/Statistician Reviewers
- **Fast 模型**: 简单分类任务 (未使用但支持)

## 🔒 安全与合规

- ✅ 所有稿件数据加密存储和传输
- ✅ Prompt Injection 防护
- ✅ 不编造引用（所有证据可追溯）
- ✅ 低置信度判断明确标注
- ✅ AI 辅助声明（报告中明确标注）

## 📊 预期性能指标

| 指标 | 目标值 |
|-----|-------|
| 端到端延迟 (8000词论文) | < 3 分钟 |
| 结构化信息提取准确率 | > 95% |
| 研究类型识别准确率 | > 98% |
| 单 Block 处理延迟 | < 20 秒 |
| 已知攻击模式检出率 | 100% |

## 🛠️ 开发与测试

```bash
# 运行测试
pytest tests/

# 查看可用 Rubrics
python -c "from src.utils import RubricLoader; loader = RubricLoader(); print(loader.list_available_rubrics())"

# 查看 Rubric 详情
python -c "from src.utils import RubricLoader; loader = RubricLoader(); print(loader.get_rubric_metadata('consort_2010'))"
```

## 📝 扩展开发指南

### 添加新的 Checklist

1. 在 `src/rubrics/` 目录创建新的 YAML 文件
2. 按照现有格式定义评估项
3. 在 `RubricLoader` 中添加研究类型映射

示例:

```yaml
# src/rubrics/prisma_2020.yaml
name: PRISMA 2020
version: "1.0"
applicable_to:
  - Systematic Review
  - Meta-Analysis

items:
  - item_id: PRISMA_1
    item_number: "1"
    category: Title
    question: "Does the title identify the report as a systematic review?"
    evaluation_criteria: "Title should contain 'systematic review' or similar term."
    evidence_location_hint: "title"
    severity_if_missing: MINOR
```

### 添加新的 Agent

继承 `MethodologyReviewerAgent` 或创建新的 Agent 类，实现特定领域的审稿逻辑。

## 📄 许可证

本项目基于设计文档"ai论文评审.md"实现，用于学术研究和教育目的。

## 🤝 贡献

欢迎贡献新的 Checklist、优化建议和 Bug 修复。

## 📧 联系方式

如有问题或建议，请提交 Issue。

---

**免责声明**: 本系统为辅助工具，所有判断和建议仅供参考，不替代人类专家的专业审稿。最终的稿件质量评估和发表决策应由合格的同行评议专家做出。