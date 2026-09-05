<p align="center">
  <img src="docs/social-preview.png" alt="ResearchPal · AI 科研助手" width="100%">
</p>

<p align="center">
  <a href="https://researchpal-inky.vercel.app">
    <img src="https://img.shields.io/badge/%F0%9F%9A%80%20%E5%9C%A8%E7%BA%BF%20Demo-researchpal--inky.vercel.app-1A56E8?style=for-the-badge&logo=vercel&logoColor=white" alt="在线 Demo">
  </a>
  &nbsp;
  <a href="https://github.com/AAly030120/ResearchPal">
    <img src="https://img.shields.io/badge/GitHub-%E6%BA%90%E7%A0%81-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub 源码">
  </a>
</p>

<p align="center">
  <a href="#-快速开始"><strong>▶ 本地一键体验（无需 API Key）</strong></a>
  &nbsp;·&nbsp;
  <a href="docs/PRODUCT.md">📋 产品决策</a>
  &nbsp;·&nbsp;
  <a href="docs/INTERVIEW.md">🎤 面试故事库</a>
  &nbsp;·&nbsp;
  <a href="docs/GITHUB_LAUNCH.md">🚀 推送指引</a>
</p>

# ResearchPal · AI 科研助手

> 面向高校学生的 **AI 驱动科研工作台**——把文献阅读、数据分析、报告撰写、演示制作等繁琐学术流程，一站式自动化。

[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#license)
[![Demo](https://img.shields.io/badge/Demo-无需%20API%20Key-blue)](#%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B)

## 📑 目录

- [这是什么](#这是什么)
- [🖼️ 界面预览](#-界面预览)
- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [🚀 快速开始](#-快速开始)
- [目录结构](#目录结构)
- [工程亮点](#工程亮点)
- [文档导航](#文档导航)
- [Roadmap](#roadmap)
- [License](#license)

---

## 这是什么

ResearchPal 是一款 **全栈 AI 产品**：用户上传论文 / 数据 / 文档，平台调用大语言模型完成**文献总结、数据分析与图表、一键生成 PPT、代码生成、文件翻译**五大任务，并配备账号体系、多模型切换与个性化记忆。

它既是可用的科研工具，也是一个展示 **AI 产品设计 + 工程落地** 能力的作品项目。关于背后的用户研究、功能优先级、模型选型权衡与成功指标，见 [**PRODUCT.md**](docs/PRODUCT.md)。

> 💡 **零配置即可体验**：不填任何 API Key 也能跑通全部功能（Demo 模式会返回示例结果，数据分析甚至会在隔离沙箱里真实执行并出图）。详见下方「快速开始」。

---

## 🖼️ 界面预览

**落地页** —— 一句话讲清价值主张，5 秒决定要不要注册。

![ResearchPal 落地页](docs/screenshots/home.png)

**五大工具**（已登录真实界面）：

| | |
| :---: | :---: |
| **📄 文献总结** — 上传 PDF/Word，一键结构化摘要 + 多种引用格式<br>![文献总结](docs/screenshots/tool-summary.png) | **📊 数据分析** — 上传 CSV/Excel，LLM 生成代码 → 沙箱执行出图<br>![数据分析](docs/screenshots/tool-analysis.png) |
| **🎨 PPT 制作** — 自然语言描述风格，自动生成 `.pptx`<br>![PPT 制作](docs/screenshots/tool-ppt.png) | **💻 代码生成** — 自然语言需求 → 代码 → 一键执行<br>![代码生成](docs/screenshots/tool-code.png) |
| **🌐 文件翻译** — PDF/Word 保留原排版的中英互译<br>![文件翻译](docs/screenshots/tool-translate.png) | **💬 AI 对话** — 基于历史任务的个性化记忆<br>![AI 对话](docs/screenshots/chat.png) |

---

## 功能特性

| 功能 | 说明 |
| --- | --- |
| 📄 **文献总结** | 上传 PDF / Word，输出结构化摘要、关键贡献、方法学与文献元数据，支持中/英输出与多种引用格式 |
| 📊 **数据分析** | 上传 CSV / Excel，LLM 生成 pandas 分析代码 → 隔离沙箱执行 → 捕获图表与统计摘要 |
| 🎨 **PPT 制作** | 自然语言描述风格，自动生成大纲与配色，导出可编辑的 `.pptx`（6 种版式，零依赖可降级） |
| 💻 **代码生成** | 自然语言需求生成 Python 代码，可一键在沙箱中执行并返回结果 |
| 🌐 **文件翻译** | 支持 PDF / Word / 文本，保留原排版结构的中英互译 |
| 💬 **AI 对话** | 基于历史任务的个性化记忆，越用越懂你 |
| 🔑 **多模型路由** | 统一适配 OpenAI / DeepSeek / 智谱 GLM / 通义千问，前端一键切换 |
| 👤 **账号体系** | 邮箱注册登录、JWT 鉴权、文件与任务历史与账号绑定 |

---

## 系统架构

```mermaid
flowchart LR
  U[用户浏览器] --> F[Next.js 15 前端]
  F --> G[FastAPI 网关\nJWT·校验·CORS]
  G --> DB[(SQLite/Postgres\n用户·文件·任务·画像)]
  G --> LLM[LLM 服务层\n多模型路由·流式·重试]
  G --> SB[代码沙箱\n隔离执行·图表捕获]
  G --> FP[文件解析/转换\nPDF·DOCX·CSV]
  G --> PPT[引用 & PPT 构建\nAPA/MLA·SVG→pptx]
  LLM --> EXT[外部 LLM API\nOpenAI/DeepSeek/GLM]
```

![架构图](docs/architecture.svg)

> 完整数据流与模块职责见 [**PRODUCT.md · 技术架构**](docs/PRODUCT.md#技术架构与关键决策)。

---

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Next.js 15 (App Router) · React 19 · Tailwind CSS · shadcn/ui · SSE 流式 |
| 后端 | FastAPI · SQLAlchemy 2.0 · python-jose (JWT) · bcrypt |
| AI | OpenAI / DeepSeek / 智谱 GLM / 通义千问（统一 OpenAI-compatible 适配）· tenacity 重试 |
| 文件 | pdfplumber · python-docx · pandas · openpyxl |
| 图表 | matplotlib · seaborn（沙箱内执行） |
| 演示 | python-pptx（内置渲染器，可选 ppt-master 提升保真度） |
| 部署 | Render（`render.yaml` 已就绪）· 支持 Docker |

---

## 快速开始

### 方式一：零配置体验（推荐先试）

```bash
# 1. 后端
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2. 前端（另开一个终端）
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

打开 `http://localhost:3002`，**不填任何 API Key** 即可：
- 注册 / 登录账号
- 跑通全部 5 个工具（总结 / 分析 / PPT / 代码 / 翻译）
- 下载真实的 `.pptx`、查看真实的分析图表（沙箱执行）

> 未配置 Key 时进入 **Demo 模式**：结构化任务返回示例结果，数据分析仍会在隔离沙箱中真实运行并出图，方便评审人一键体验产品闭环。

### 方式二：接入真实大模型

复制 `backend/.env.example` 为 `backend/.env`，填入至少一个模型的 API Key（如 `DEEPSEEK_API_KEY`），重启后端即可切换为真实 AI 输出。模型可在前端「设置」页随时切换。

---

## 目录结构

```
researchpal/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # 路由层（auth/files/tasks/chat/settings）
│   │   ├── core/            # 配置、安全、密钥管理
│   │   ├── models/          # SQLAlchemy 模型
│   │   ├── schemas/         # Pydantic 模式
│   │   └── services/        # 业务逻辑（LLM/沙箱/PPT/引用/翻译/记忆/Demo）
│   └── requirements.txt
├── frontend/                # Next.js 前端
│   └── src/app/             # 页面（工具页 / 聊天 / 账号 / 设置）
├── docs/
│   ├── architecture.svg     # 架构图
│   ├── PRODUCT.md           # 产品决策文档
│   └── INTERVIEW.md         # 简历要点 & 面试题回答库
├── render.yaml              # 一键部署（Render）
└── .gitignore
```

---

## 工程亮点

- **多模型统一适配**：所有 provider 适配为 OpenAI-compatible 接口，切换成本为零；前端可热切换，后端自动回退到首个可用 Key。
- **代码沙箱隔离**：数据分析 / 代码执行在受限子进程中运行，禁用危险模块、限制超时，捕获 stdout 与图表，安全可审计。
- **引用格式严谨**：`citation_service` 实现 APA / MLA / Chicago / GB7714 四种规范，按规范严格格式化。
- **PPT 零依赖可降级**：内置 python-pptx 渲染器，缺失可选 ppt-master 时自动降级，克隆即跑、绝不崩。
- **个性化记忆**：`memory_service` 随使用积累用户风格与领域偏好，注入后续 LLM 提示词，产品越用越聪明。
- **Demo 模式**：无 Key 也能完整演示，降低评审与协作门槛。

---

## 文档导航

- [PRODUCT.md](docs/PRODUCT.md) — 用户研究、功能优先级、模型选型成本权衡、成功指标、AI 安全与学术诚信
- [INTERVIEW.md](docs/INTERVIEW.md) — 简历要点写法 + 高频面试题回答库（为什么做 / 最大权衡 / 如何度量 / AI 安全思考）
- [GITHUB_LAUNCH.md](docs/GITHUB_LAUNCH.md) — 推送前的门面清单：About 文案 / Topics / 社交预览图上传步骤 / 推送 checklist
- [架构图](docs/architecture.svg)

---

## Roadmap

- [ ] 任务队列（Celery + Redis）支持大文件后台异步
- [ ] 基于上传文档的 RAG 多轮问答
- [ ] 管理后台：模型 Key 管理与用量统计
- [ ] 更多引用格式与期刊模板

---

## License

[MIT](LICENSE) © ResearchPal
