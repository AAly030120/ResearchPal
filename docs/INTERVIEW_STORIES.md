# ResearchPal · 面试 STAR 故事库

> 用法：面试官问「印象最深的技术难点 / 最大权衡 / 遇到什么坑」时，用下面的 STAR 结构回答。
> 每个故事都是项目里**真发生过**的事，可直接讲。括号内是引导追问的钩子。

---

## 故事 1 · Render 临时文件系统把用户「清空」了（SRE / 持久化）

- **Situation**：把 ResearchPal 部署到 Render Free 计划做面试 Demo。Free 实例的磁盘是**临时的**，每次冷启动/重启 `uploads/`、`outputs/`、`chroma_store/`、SQLite 库全被清空。
- **Task**：上线后用户反馈「忘记密码后账号没了、上传的文献消失了」，而我本地一切正常。
- **Action**：
  1. 先定位根因：本地用持久盘、云端用临时盘，环境差异导致；
  2. 把文件原始字节存进 Postgres 的 `BYTEA` 列（`File.data`），重启后 `materialize_file()` 自动还原到磁盘，无需重新上传；
  3. 用独立的 Postgres 服务（不受实例重启影响）替代本地 SQLite，`render.yaml` 声明 `databases` 自动注入 `DATABASE_URL`；
  4. Chroma 向量库加启动自愈：lifespan 后台线程为「已索引但向量缺失」的文件重建索引。
- **Result**：重启不再丢数据；并开源了 `backend/scripts/seed_demo.py` 一键预置演示账号。
- **钩子**：「Free 方案不支持持久卷，挂上 $7/mo 的 Starter 卷就更简单——但我用 Postgres BYTEA 零成本解决了。」

---

## 故事 2 · 一个没带 workflow 作用域的 PAT，把我刚写的 CI 挡在门外（DevOps / 安全）

- **Situation**：项目早期用普通 `repo` 作用域的 PAT 推代码，CI workflow 文件被悄悄从推送历史里剥离（推不上去），CI 一直没跑。
- **Task**：恢复 GitHub Actions 测试流水线，且要保证以后能持续跑。
- **Action**：
  1. 把 CI 配置副本保留在 `docs/ci-workflow.yml` 作为灾后恢复备份；
  2. 用户提供了带 `workflow` 作用域的 PAT 后，恢复 `.github/workflows/ci.yml` 并推送；
  3. 第一次推送被沙箱网络拦截（github.com:443 不可达），改用带授权的网络通路完成推送；
  4. 推送后发现 CI 仍失败——`requirements.txt` 没含 `pytest`，workflow 里补了 `pip install pytest`。
- **Result**：CI 转绿，13 项测试（9 RAG/GraphRAG + 4 安全）每次 push/PR 自动跑。
- **钩子**：「这也顺带提醒我：PAT 用完即吊销，三个 token 都该立刻撤销。」

---

## 故事 3 · Python 3.14 装不上 fastembed（依赖/版本治理）

- **Situation**：部署环境的 Python 被解析成 3.14，而 `fastembed` / `chromadb` 的 Rust 预编译 wheel 还没有 3.14 版本，构建直接失败。
- **Task**：让依赖可安装、CI 可复现。
- **Action**：在 `render.yaml` 与 CI 显式锁定 **Python 3.11**（有完整 wheel 支持），并在文档标注版本约束；本地用托管 venv 只装轻量依赖跑逻辑测试，CI 用完整依赖。
- **Result**：部署与 CI 都稳定；构建时间可控。
- **钩子**：「版本锁不是保守，是给未来的自己少埋坑。」

---

## 故事 4 · 代码沙箱先装钩子后加载库，用户代码跑了真正的逃逸通道（安全）

- **Situation**：论文数据分析功能用 Python 沙箱跑用户上传的代码。初版有个连锁缺陷。
- **Task**：在「能真实出图」和「不被逃逸」之间拿平衡。
- **Action**：
  1. 修正加载顺序——先让库正常 import，再装安全钩子，并把 `os`/`sys`/`importlib` 移出拦截名单（库硬依赖，拦了没安全收益反而崩）；
  2. 结果标记改用 `sys.__stdout__` + 注册 `sys.excepthook`，避免用户代码污染输出；
  3. 真正危险的逃逸通道（`subprocess`/`socket`/`ctypes`/`multiprocessing`）仍被拦截，并写了测试验证。
- **Result**：沙箱既能在隔离环境里真实执行 `matplotlib` 出图，又挡住系统级逃逸；相关修复已提交并部署。
- **钩子**：「安全不是把门焊死，是只焊该焊的那几扇。」

---

## 故事 5 · 为什么是 GraphRAG 而不是再加一个向量库（产品/技术权衡）

- **Situation**：基线 RAG（Chroma 向量 + jieba 关键词重排）已能跑，但文献里「A 的方法基于 B 的理论」这种**间接关系**向量检索经常漏掉。
- **Task**：决定要不要上 GraphRAG，以及怎么上。
- **Action**：
  1. 做了开源调研（open-webui / RAGFlow / paper-qa / AnythingLLM），确认重排 + 父子分块 + 多召回融合是行业共识，先做这两项（Top-3 增强）；
  2. 把另一个项目 LitKG 的知识图谱抽取/社区发现/N 跳检索**融合**进来，复用现有 `llm_service` 而非独立客户端；
  3. 图谱存 Postgres（不是 JSON 文件），保证 Render 重启后存活；
  4. 写了 `bench_rag.py` 量化：当首轮检索失败时，GraphRAG 的 N 跳扩展把 Recall@1 从 0.00 拉回 0.67、Recall@5 到 1.00。
- **Result**：检索从「相似片段」升级到「关系推理」，且能量化收益。
- **钩子**：「功能做加法很容易，难的是证明它真的有用——所以我写了评测脚本而不是拍胸脯。」

---

## 速查表（被追问时兜底）

| 面试官可能问 | 一句话接法 |
|---|---|
| 你怎么衡量成功？ | 检索 Recall@K + 端到端延迟 + 演示账号开箱即用；有 `bench_rag.py` 量化 |
| 最大权衡？ | Free 部署零成本 vs 临时磁盘 → 用 Postgres BYTEA 换持久化，不花钱 |
| 最深的 bug？ | Python 3.14 无 wheel；沙箱加载顺序；CI 缺 pytest |
| 安全怎么想？ | 只拦真逃逸通道，库依赖放行；PAT 用完吊销 |
| 为什么不用 LangChain？ | 自研检索/重排/图谱更可控、依赖更轻、面试能讲清每行代码 |
