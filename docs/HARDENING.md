# ResearchPal 抗打加固：从开源标杆复刻的工程实践

> 用户原话：「这个 AI 很粗略草率不堪一击，去 GitHub 找类似开源项目，学习优势复刻到我的项目里，让项目更抗打。」
> 本文档记录调研来源、已实施的加固、以及待决策的高阶项。

## 一、调研的标杆项目与可借鉴点

| 开源项目 | 核心优势 | 复刻到的实践 |
|---|---|---|
| **open-webui** | secure-by-default、依赖安全治理、OpenTelemetry 可观测、向量库抽象 | 生产密钥强制、CVE 依赖升级、错误契约统一 |
| **paper-qa (PaperQA2)** | Pydantic Settings 集中配置、速率限制、文内引用、失败重试、混合检索 | 速率限制、LLM 超时/重试、配置集中管理 |
| **RAGFlow** | 模板化分块 + 多召回融合 + 重排、解析失败不静默丢弃 | （规划中）RAG 检索增强 |
| **AnythingLLM** | 双服务解析隔离、统一错误契约 `success:false` | 统一异常处理 + 错误契约 |
| **gpt-researcher** | 多代理审校流水线、SSRF/本地文件读取防护 | （规划中）多代理审校 |

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

## 三、验证结果

- 6/6 测试通过（下载鉴权/越权/穿越、沙箱密钥剥离、生产密钥强制、dev 空密钥放行）
- 生产模式启动冒烟：`/api/health` 返回 production、未登录下载 401、限流中间件激活

## 四、待决策的高阶项（需你拍板）

- [ ] **RAG 检索增强（最高价值，但改动大）**
  当前 chat / 文献总结是把上传文档文本**直接拼接进 prompt（上限 30000 字符）**：
  长文被截断、跨文档无去重、无语义检索——这是核心功能在真实科研场景最脆弱处。
  计划：引入向量库（Chroma）+ 文档分块 + Embedding + 检索 + 重排，复刻 RAGFlow/paper-qa。
  ⚠️ 会影响核心对话链路，且需评估 Demo 离线运行（无外部 Embedding 服务时降级）。

- [ ] **双服务解析隔离**（AnythingLLM）：大文件解析移到独立 worker，避免阻塞主链路。

- [ ] **密钥落盘加密**：`.api_keys.json` 目前明文（已 gitignore 但工作区明文），建议仅用环境变量或加密存储。

## 五、部署注意（重要）

本次改动**强化了生产安全**。若推送到 Render：
- 必须在 Render 环境变量中设置 `SECRET_KEY`（Generate 一个随机串），否则后端将以
  `ValueError: SECURITY: SECRET_KEY must be set in production` **启动失败**。
- `DEBUG` 应保持 `false`（你之前已设）。
