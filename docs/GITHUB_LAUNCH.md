# GitHub 推送指引（让仓库在面试官眼里「发光」）

> 这一页专门给「点进 GitHub 链接看到的那屏」做最后一遍把关。逐项填完后，仓库首屏就足以让面试官 3 秒内决定继续读。

---

## 1. 仓库名

推荐：`researchpal` 或 `ai-research-assistant`。短、能搜到、不含用户名后缀。

---

## 2. About 描述（粘到 GitHub → Settings → General → About → **Description**）

英文版（推荐，英文简历/外企团队也通用）：

```
AI-driven research workbench: summarize papers, analyze data, generate PPTs,
write code, and translate documents in one place. Full-stack AI product
(FastAPI + Next.js 15) with zero-config Demo mode — clone & run.
```

中文版（若你的目标公司以中文为主）：

```
面向高校学生的 AI 科研工作台：一站式完成文献总结、数据分析与图表、PPT 制作、代码生成与文件翻译。全栈 AI 产品（FastAPI + Next.js 15），零配置即可体验。
```

---

## 3. Topics（粘到同页 Tags 输入框，回车确认。建议选 5–8 个）

```
ai
llm
nextjs
fastapi
research
academic
pptx
data-analysis
```

可选加分项（看你想强化哪一面）：

```
shadcn-ui
product-management
```

---

## 4. Website / Demo 链接

填 `https://researchpal.onrender.com`（你 Render 部署拿到的 live URL）。
未上线前可先填仓库 Pages 地址或留空。

> **关键**：有 live demo 是这个项目最强的加分项。一键点开比任何截图都可信。

---

## 5. Social preview 图（让仓库卡片不再灰扑扑）

`docs/social-preview.png` 已生成（1280×640，已就绪）。

操作：
1. 进入 GitHub 仓库 → **Settings** → **General** → **Social preview**
2. 点击 **Upload an image** → 选择 `docs/social-preview.png`
3. 保存后，**README 顶部和分享卡片**都会用这张图替换默认灰块。

> 这张图是面试官把链接发到群里 / 在 LinkedIn 分享时的预览——是「门面照」，必传。

---

## 6. 推送前 Checklist（逐项勾）

- [ ] **截图就位**：`docs/screenshots/` 下至少有 `home.png`、`summarize.png`、`analysis.png`、`ppt.png`、`code.png` 5 张（运行应用 + 浏览器截图得到，README 会自动展示）
- [ ] **README 首屏**：已嵌入一张产品 hero 图 + 醒目「▶ 在线 Demo」按钮（部署后填真实链接）
- [ ] **无密钥被跟踪**：`git ls-files | grep -iE "\.env$|\.env\.local|\.db$|api_keys"` 输出为空（已确认）
- [ ] **LICENSE**：MIT（已就绪）
- [ ] **render.yaml + .env.example**（已就绪）
- [ ] **社交预览**已上传（见 §5）
- [ ] **About 描述 + Topics + Website** 已填（见 §2/§3/§4）

---

## 7. 推送步骤

```bash
# 在你的新 GitHub 仓库创建好（建议空仓，不要勾 README/gitignore/License）

cd researchpal
git remote add origin https://github.com/<你的用户名>/researchpal.git
git branch -M main
git push -u origin main

# （可选）把默认分支改回 main，并启用 Issues / Discussions
```

---

## 8. 推送后建议立刻做的 3 件事

1. **Pin 一个 Issue / Discussion**：「📋 Interview Walkthrough」——把你的简历 bullet 粘进去，并 @自己，方便面试官一眼看到你的「自荐导读」。
2. **Releases**：打一个 `v1.0.0` Release，标题写成 `ResearchPal v1.0 · AI research workbench`。面试官在仓库首页会看到「Latest release」标签，这是工程成熟度的暗示。
3. **GitHub Topics 二次确认**：推送后回到仓库首页 → 右侧栏 Topics 实际渲染正常（有时需要刷新缓存）。

---

## 9. 万一面试官要现场跑 / 问你 Demo

准备 3 句话讲法（直接照读）：

1. **「零配置就能跑」** — "我加了 DEMO_MODE：clone 后不填任何 API Key 也可以跑完所有 5 个工具，PPT 也能下载真实 .pptx、数据分析会在隔离沙箱里真实执行出图。这是为面试官降低体验门槛做的设计。"
2. **「PPT 不会因为克隆就崩」** — "项目原本依赖一个本地 80MB 的 PPT 技能目录（被 gitignore 排除），我把它换成了零依赖的 python-pptx 渲染器做降级——这是发布到 GitHub 前必须修的工程债。"
3. **「这是 AI 产品岗的作品」** — "我做的不只是程序——`docs/PRODUCT.md` 写了用户研究、RICE 优先级、模型选型成本权衡、AI 安全与学术诚信；`docs/INTERVIEW.md` 有 8 道高频面试题的回答框架。"

---

最后，**README 是 3 秒 / 30 秒 / 5 分钟漏斗**：
- 3 秒：社交预览图 + 一句话定位 + badges
- 30 秒：功能表 + 架构图 + 「零配置体验」承诺
- 5 分钟：用户研究 / 优先级 / 模型权衡 / 成功指标 → 看你是不是 PM

这张网已经在本仓库里织好了，你只需要把它推上去。