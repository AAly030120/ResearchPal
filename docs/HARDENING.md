# ResearchPal 抗打加固：从开源标杆复刻的工程实践

> 用户原话：「这个 AI 很粗略草率不堪一击，去 GitHub 找类似开源项目，学习优势复刻到我的项目里，让项目更抗打。」
> 本文档记录调研来源、已实施的加固、以及待决策的高阶项。

## 一、调研的标杆项目与可借鉴点

| 开源项目 | 核心优势 | 复刻到的实践 |
|---|---|---|
| **open-webui** | secure-by-default、依赖安全治理、OpenTelemetry 可观测、向量库抽象 | 生产密钥强制、CVE 依赖升级、错误契约统一 |
| **paper-qa (PaperQA2)** | Pydantic Settings 集中配置、速率限制、文内引用、失败重试、混合检索 | 速率限制、LLM 超时/重试、配置集中管理 |
| **RAGFlow** | 模板化分块 + 多召回融合 + 重排、解析失败不静默丢弃 | 已实施：父子分块 + 交叉编码器重排（Top-1/2） |
| **AnythingLLM** | 双服务解析隔离、统一错误契约 `success:false` | 统一异常处理 + 错误契约 |
| **gpt-researcher** | 多代理审校流水线、自动规划子问题、深度研究 | 已实施：深度研究 Agent（规划→检索→合成→参考来源） |
| **LitKG（自有项目）** | 实体/关系抽取 + NetworkX 图谱 + Louvain 社区发现 | 已融合：GraphRAG 知识图谱增强 |

## 二、已实施并测试锁定（本轮）

### P0 · 安全（6 项自动化测试全部通过）

1. **生产环境 SECRET_KEY 强制** — `backend/app/core/config.py`
   `model_validator` 在 `DEBUG=false`（生产）且无 SECRET_KEY 时**拒绝启动**。
   复刻 open-webui / paper-qa 的 *secure-by-default*。

2. **任务结果下载接口鉴权 + 所有权 + 路径穿越防护** — `backend/app/main.py`
   原接口无鉴权、可枚举 task_id 下载他人文件、且无路径规范化（潜在穿越）。
   现：必须登录 → 校验 `task.user_id == current_user.id` → `os.path.normpath` 限制在 cwd 内。

3. **沙箱子进程剥离密钥环境变量** — `backend/app/services/sandbox.py`
   原 `env={**os.environ}` 把 `SECRET_KEY`/`DATABASE_URL`/各家 API Key 全量传给沙箱。
   现：构造时显式剔除这些敏感键，子进程只读 PATH/TEMP 等系统变量。
   *测试已验证子进程 `os.environ` 中 `SECRET_KEY`/`DATABASE_URL` 均为 `false`。*

### P1 · 工程健壮性

4. **LLM 调用超时与重试** — `backend/app/services/llm_service.py`
   `AsyncOpenAI(timeout=60.0, max_retries=3)`，防止上游挂起拖垮后端（原客户端无 timeout，默认约 10 分钟）。

5. **全局速率限制** — `backend/app/main.py` + `requirements.txt`(slowapi)
   全局 120 req/min，防暴力破解与资源耗尽（paper-qa 思路）。

6. **统一异常处理 + 错误契约** — `backend/app/main.py`
   未捕获异常返回 `{"success": false, "detail": ...}`；**生产模式不泄露 traceback**
   （AnythingLLM 的统一错误契约 + 防信息泄露）。

7. **依赖与默认值加固**
   - `python-multipart` 0.0.12 → **0.0.18**（修复 CVE-2024-24762 DoS）
   - `DEBUG` 默认 dev（保留零配置体验），但生产强制校验密钥

8. **基础测试 + CI** — `backend/tests/` + `.github/workflows/ci.yml`
   6 项安全回归测试，push/PR 自动跑（open-webui 风格的回归防护）。

### P2 · RAG 增强（Top-3 + GraphRAG，复刻 RAGFlow / gpt-researcher / LitKG）

9. **父子分块（Parent-Child Chunking）** — `backend/app/services/rag_service.py`
   子块（≤320 字）用于向量检索、父块（≤700 字）作为注入 LLM 的生成上下文窗口，
   配套页码级元数据（`pages`），回答可标 `[来源: 文件名 第N页 #片段M]`。
   复刻 RAGFlow 的「模板化分块 + 大上下文」思路。

10. **交叉编码器重排（Cross-Encoder Reranker）** — `backend/app/services/reranker.py`
    检索后用 fastembed `bge-reranker-v2-m3` 对 Top 候选做 (query, passage) 重打分；
    fastembed 缺失 / 模型加载失败时**优雅降级**为「余弦 + jieba 关键词」启发式，零外部依赖也能跑。

11. **知识图谱 GraphRAG（融合 LitKG）** — `backend/app/services/kg_*.py` + `backend/app/api/kg.py`
    抽取 10 类实体 / 10 类关系 → Postgres 持久化 + NetworkX 内存图；对话时沿图谱 **N 跳扩展**
    检索上下文，Louvain 社区发现 + LLM 主题摘要，单文件范围检索。复用本平台 `llm_service`。

12. **深度研究 Agent** — `backend/app/services/research_service.py` + `POST /api/chat/research`
    规划子问题 → 并行检索向量库与知识图谱 → 逐章流式合成 → 自动汇总参考来源；SSE 实时进度。
    复刻 gpt-researcher 的多步研究流水线。

## 三、验证结果

- 13/13 测试通过（6 项安全回归 + 7 项新增 RAG/GraphRAG/深度研究逻辑测试）
  - 新增 `backend/tests/test_rag_kg.py`：父子分块、重排器降级、图谱 N 跳扩展、深度研究 pipeline（LLM/检索均 mock）
- 生产模式启动冒烟：`/api/health` 返回 production、未登录下载 401、限流中间件激活
- 生产模式启动冒烟：`/api/health` 返回 production、未登录下载 401、限流中间件激活

## 四、待决策的高阶项（需你拍板）

- [x] **RAG 检索增强（最高价值）** — 已完成：Chroma 向量库 + 父子分块 + Embedding（本地 fastembed / DashScope）+ 检索 + 交叉编码器重排 + 页码级引用；Demo 离线（无外部 Embedding）时自动降级启发式。详见上方 P2 第 9–10 项。

- [ ] **双服务解析隔离**（AnythingLLM）：大文件解析移到独立 worker，避免阻塞主链路。

- [x] **密钥落盘加密**：`.api_keys.json` 由明文改为 **Fernet 加密存储**——密钥由 `SECRET_KEY` 派生（生产）或内置 dev fallback（开发，避免明文落盘），多 key 容错；兼容旧明文格式自动迁移、损坏文件安全丢弃。新增 `tests/test_key_encryption.py`（5 项）锁定「明文不落盘 / 跨实例解密 / 旧格式迁移 / 损坏恢复 / 删除即清」。

## 五、部署注意（重要）

本次改动**强化了生产安全**。若推送到 Render：
- 必须在 Render 环境变量中设置 `SECRET_KEY`（Generate 一个随机串），否则后端将以
  `ValueError: SECURITY: SECRET_KEY must be set in production` **启动失败**。
- `DEBUG` 应保持 `false`（你之前已设）。
