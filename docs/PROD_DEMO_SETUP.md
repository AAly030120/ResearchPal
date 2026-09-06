# 线上演示运行时配置（Render 侧）

> 目标：让面试官打开 https://researchpal.onrender.com 或 https://researchpal-inky.vercel.app
> 时，**无需任何配置即可跑通完整流程**（注册/上传已预置、知识图谱已建好、LLM 能实时回答）。
>
> 本文件只讲「生产环境运行时怎么配」，演示剧本本身见 [DEMO_SCRIPT.md](./DEMO_SCRIPT.md)，
> 架构与故事见 [INTERVIEW_STORIES.md](./INTERVIEW_STORIES.md)。

---

## 一、要配什么（手动 Web Service 必须 4 个变量）

> ⚠️ **关键提醒**：你用的是 **Manual Web Service**（非 Blueprint 自动部署），所以 `render.yaml` 里的 `envVars` 和 `databases` **不会被 Render 自动读取**。因此 `DATABASE_URL` 与 `SECRET_KEY` 都不会自动注入，**必须手动在面板里加**。

### 步骤 0：先确认 Postgres 数据库

Render Dashboard 左侧 → **PostgreSQL**。如果你已经有一个 `researchpal-db`（或任何 Postgres）服务，点进去 → **Info** → **External Database URL** → 复制那串 `postgresql://...`。

如果没有 Postgres 服务：
1. 点击 **New +** → **PostgreSQL**，名字写 `researchpal-db`，plan 选 **Free**。
2. 创建后复制 **External Database URL**。
3. 把它加到后端服务的环境变量里（见下表）。

### 步骤 1：给 `researchpal-api` 加环境变量

Render Dashboard → 你的 `researchpal-api` 服务 → **Environment** 里添加/修改：

| 变量 | 值 | 说明 |
|---|---|---|
| **`DATABASE_URL`** | 上面复制的 `postgresql://...` | **必须先设**。不配置会退回到 SQLite，文件存在 Render 临时磁盘，休眠后账号/文件全丢 |
| `SECRET_KEY` | 任意强随机字符串，例如 `openssl rand -hex 32` | 生产模式(`DEBUG=false`)必须，否则后端拒绝启动。可在本地生成后粘贴 |
| `OPENAI_API_KEY` | 你的 OpenAI Key | 默认模型 `gpt-4o-mini` 走这里。**至少要有一个 LLM Key**，否则会退回演示占位文案 |
| `CORS_ORIGINS` | `https://researchpal-inky.vercel.app` | 前端域名（已配则忽略）。**不带尾斜杠** |
| `SEED_DEMO` | `1` | 设为 `1` 后，服务每次冷启动会**自动预置演示账号**（见下），配一次永久生效 |

可选补充：

- 不想用 OpenAI，可改用 `DEEPSEEK_API_KEY` 或 `GLM_API_KEY`，并把 `DEFAULT_MODEL` 改成对应模型名（如 `deepseek-chat`）。
- 改 Environment 变量后 Render 会**自动触发一次新的 Build/Deploy**，等 Deploy 变绿后再验证。
- 如果之后看到 `sqlite3.OperationalError duplicate column name` 之类的日志，说明 `DATABASE_URL` 还是没配对、后端仍在用 SQLite；请回来检查这一步。

---

## 二、`SEED_DEMO=1` 做了什么（自动预置演示账号）

设为 `1` 后，`app/main.py` 的 lifespan 在启动时（后台线程、非阻塞、失败不影响服务）调用
`scripts/seed_demo.py::run_seed()`，自动完成：

1. 创建演示账号 `demo@researchpal.dev` / `demo1234`（已存在则**整段跳过**，不重复建图）。
2. 写入 3 篇示例文献（分子图神经网络 / MPNN / 知识图谱嵌入方向）到数据库 **BLOB 列** `File.data`。
3. 在实例内本地建立向量索引（Chroma），并把 `File.indexed=True` 写回数据库。
4. 写入一份**预置知识图谱**（25 实体 / 28 关系 + 社区摘要），无需 LLM、离线即可。
5. 控制台打印：`演示账号就绪 / 登录: demo@researchpal.dev / demo1234 / 图谱: 25 实体 / 28 关系`。

**为什么这样设计能扛 Render 重启**：
- Render Free 的磁盘是临时的，重启后 `uploads/`、`chroma_store/` 会被清空；
- 但 Postgres 里的账号、文件 BLOB、图谱、`indexed` 标记都还在；
- 下次启动 `rag_service.heal_indexes()` 看到 `indexed=True` 但向量缺失，会**从 BLOB 自动重建向量索引**。
- 演示账号同理：`SEED_DEMO` 检测到账号已存在就跳过，不会重复劳动。

强制重建（换文献/换图谱时）：把 `SEED_DEMO_RESET` 也设为 `1` 触发一次，之后可改回 `0`。

---

## 三、验证是否生效

部署变绿后，任选其一验证：

**A. 看启动日志**
Render → Logs 里应出现：
```
Demo seeding scheduled (SEED_DEMO=1)
[+] 创建演示账号: demo@researchpal.dev / demo1234
[+] 图谱已写入: ... (9 实体 / 11 关系)
演示账号就绪
```

如果还看到 `sqlite3.OperationalError duplicate column name`（你截图里的红色告警），
说明 `DATABASE_URL` 没配对、后端仍在用 SQLite。请回到「步骤 0」把 Postgres 外部连接串填上并重新部署。

你还会看到一条 `chromadb.telemetry.product.posthog Failed to send telemetry event` 的 ERROR——
这是 ChromaDB 与新版 PostHog 兼容性的**上游已知问题**，不影响检索与建图，可以忽略。

**B. 用演示账号走一遍检索（最稳的冒烟测试）**
```bash
# 1) 登录拿 token
TOKEN=$(curl -s -X POST https://researchpal.onrender.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@researchpal.dev","password":"demo1234"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2) 列文件，确认 3 篇示例文献已预置
curl -s https://researchpal.onrender.com/api/files -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 3) 触发一次检索，确认返回带引用的答案（证明 Key + 索引都通）
curl -s -X POST https://researchpal.onrender.com/api/chat/...   # 见 DEMO_SCRIPT.md
```

**C. 直接打开前端**：用 `demo@researchpal.dev` / `demo1234` 登录，进「知识图谱」应直接看到图谱，进「对话/RAG」应能基于示例文献回答。

---

## 四、备选方案：不从启动自种，而是本地手动 seed

如果你**不想**用 `SEED_DEMO`（例如想精确控制时机），也可以从本地机器直接对生产库 seed。
前提：本地能连到 Render Postgres 的**外部连接串**（Render Dashboard → 数据库 → External Connection String）。

```bash
cd backend
# 用生产库外部连接串（postgresql://...）连过去；UPLOAD_DIR 用默认相对路径即可，
# 存储路径和 Render 实例一致（相对 uploads/），重启后由 materialize_file 从 BLOB 还原。
DATABASE_URL="postgresql://user:pass@host:5432/researchpal" \
  python scripts/seed_demo.py

# 想真正跑 LLM 抽取图谱（而非预置图谱）就加 --with-llm，前提生产已配 Key：
DATABASE_URL="postgresql://user:pass@host:5432/researchpal" \
  python scripts/seed_demo.py --with-llm

# 重跑/清理：
python scripts/seed_demo.py --reset        # 清空演示数据并重建
```

> 注：本地手动 seed 时向量索引建在**你本机**的 `chroma_store/`，对 Render 实例无意义；
> 关键是它把 `File.indexed=True` 写进了生产库，Render 重启后由 `heal_indexes()` 自动重建线上向量。

---

## 五、安全与成本提示

- **演示账号密码是弱口令**（`demo1234`），但只用于公开演示，且数据都是示例文献，无风险。
- **共享 Key 按你的账号计费**：面试结束后建议把 `OPENAI_API_KEY` 等从 Render 移除或换受限 Key。
- **GitHub PAT**：部署用到的临时 PAT 用完即吊销，不要再保留在本地或仓库里。
- 若担心演示账号被滥用，可在面试后 `python scripts/seed_demo.py --reset` 清掉，或改 `demo@researchpal.dev` 的密码。
