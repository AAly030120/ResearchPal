#!/usr/bin/env python3
"""Seed a ready-to-demo account for ResearchPal.

Why this exists
---------------
Building the vector index and especially the knowledge graph requires an LLM
(entity extraction runs one call per file). On a live demo that means the
interviewer watches a spinner for one to three minutes — the single worst thing
that can happen in an interview.

This script front-loads all of that. After running it, the demo account already
has literature uploaded, indexed and graphed, so the live demo only exercises
*retrieval and generation*, which are fast.

Two graph modes:
  * default  — writes a curated preset graph (no LLM needed, works offline)
  * --with-llm — runs real extraction through the configured model

Usage:
    cd backend
    python scripts/seed_demo.py                 # preset graph, no key needed
    python scripts/seed_demo.py --with-llm      # real LLM extraction
    python scripts/seed_demo.py --reset         # wipe demo data and rebuild
"""

import argparse
import os
import sys
import uuid


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import File  # noqa: E402
from app.models.database import SessionLocal, engine  # noqa: E402
from app.models.kg import KGEntity, KGTriple, KGCommunity  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.database import Base  # noqa: E402

DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@researchpal.dev")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")
DEMO_USERNAME = "演示账号"

# ── Sample literature ────────────────────────────────────────────────────────
# Content is deliberately consistent with PRESET_ENTITIES / PRESET_TRIPLES below
# so that anything the graph shows can actually be traced back to the documents.

SAMPLE_DOCS = [
    {
        "name": "图神经网络在药物发现中的应用综述.md",
        "content": """# 图神经网络在药物发现中的应用综述

## 摘要

药物发现是一个周期长、成本高、失败率高的过程。传统方法依赖大量湿实验，
从先导化合物筛选到临床前研究往往需要十年以上。近年来，图神经网络（GNN）
因天然适配分子结构而被广泛用于药物发现的各个环节。本文系统梳理 GNN 在
分子性质预测、药物-靶标相互作用预测、药物重定位与药物-药物相互作用预测
四类任务上的应用，并讨论过平滑、可解释性与冷启动三个核心挑战。

## 1. 为什么分子适合用图表示

分子由原子与化学键构成，本质上就是一个图：原子是节点，化学键是边。
这种表示天然保留了拓扑结构信息，避免了 SMILES 字符串或指纹向量带来的
信息损失。早期工作使用摩根指纹（Morgan Fingerprint）作为分子表示，
但需要人工设计特征，且难以表达长程依赖。图表示学习则让模型自动从数据中
学习结构特征。

## 2. 主流模型

图卷积网络（GCN）将卷积从网格数据推广到图结构，通过邻域聚合更新节点表示。
图注意力网络（GAT）引入注意力机制，为不同邻居分配不同权重，提升了模型
对关键子结构的敏感度。消息传递神经网络（MPNN）提供了一个统一框架，
将各类图模型抽象为"消息传递-聚合-更新"三步，成为分子表示学习的事实标准。

在这些模型之上，研究者进一步提出预训练策略。通过在大规模无标注分子库
（如 ZINC，含数百万化合物）上做自监督预训练，再在具体任务上微调，
显著缓解了标注数据稀缺的问题。

## 3. 任务与数据集

分子性质预测是最成熟的应用方向，目标是预测溶解度、毒性、脂溶性等理化性质。
常用数据集包括 QM9（含 13 万个小分子的量子化学性质）与 MoleculeNet
（涵盖多个子任务的基准集合）。评价指标方面，回归任务常用 RMSE，
分类任务常用 ROC-AUC。

药物-药物相互作用预测关注联合用药时的不良反应，常用 ZINC 与公开药物
数据库构建样本。药物重定位则试图为已上市药物找到新适应症，
在突发公共卫生事件中价值突出。

## 4. 挑战与展望

过平滑是深层 GNN 的固有问题：随着层数增加，节点表示趋于一致，
区分度下降。可解释性方面，临床与监管部门需要知道模型"为什么这么预测"，
而不仅是预测结果，目前主要依靠注意力权重可视化与子结构归因。
冷启动问题则指新靶点、新骨架化合物缺乏历史数据时模型效果急剧下降。

未来的方向包括：融合三维构象信息、引入化学先验知识约束、
以及将知识图谱嵌入与分子图表示结合，同时利用结构化知识与分子结构。
""",
    },
    {
        "name": "基于消息传递神经网络的分子性质预测.md",
        "content": """# 基于消息传递神经网络的分子性质预测

## 摘要

分子性质预测是药物虚拟筛选的核心环节。本文提出一种基于消息传递神经网络
（MPNN）的分子性质预测方法，在 QM9 与 MoleculeNet 上进行了系统评测，
并分析了模型在不同性质上的表现差异与失败案例。

## 1. 方法

我们将分子建模为无向图 G = (V, E)，其中节点为原子，包含原子序数、
电荷、杂化方式等特征；边为化学键，包含键型、共轭性、环归属等特征。

模型遵循消息传递框架，包含三个阶段：

阶段一（消息传递）：对每条边，由源节点表示、边特征与目标节点表示
计算一条消息。这一步让化学键信息参与表示学习，而非仅仅作为邻接关系。

阶段二（聚合）：将每个节点收到的所有邻居消息求和。求和而非求均值，
以保留分子大小信息——这对性质预测至关重要，因为许多性质与分子量相关。

阶段三（更新）：用 GRU 更新节点隐藏状态，避免朴素 RNN 的梯度消失。

读出阶段，我们将所有节点表示送入一个 Set2Set 池化层，得到全图表示，
再接全连接层输出预测值。Set2Set 相比简单求和能保留更丰富的分布信息。

## 2. 实验设置

数据集：QM9（12 个量子化学性质回归任务）、MoleculeNet 中的
ESOL、FreeSolv、Lipophilicity（回归）与 BBBP、BACE、HIV（分类）。

基线：摩根指纹 + 随机森林、摩根指纹 + 全连接网络、GCN、GAT。

评价指标：回归任务用 RMSE，分类任务用 ROC-AUC。所有结果取三次
随机种子平均值，并报告标准差。

## 3. 结果

在 QM9 上，本方法在 12 个性质中的 9 个上优于 GCN 与 GAT 基线。
尤其在 HOMO-LUMO 能隙预测上，RMSE 相比 GCN 降低约 18%。

在 MoleculeNet 分类任务上，BBBP 的 ROC-AUC 达到 0.921，
相比摩根指纹 + 随机森林基线的 0.865 提升明显。BACE 上提升较小，
分析原因是该数据集样本量小（约 1500 条），模型容易过拟合。

值得注意的是，在 HIV 数据集上所有图模型表现都不理想。我们分析认为
该数据集极度不平衡（阳性样本约 3.5%），且存在明显的分布偏移，
单纯的架构改进难以解决，需要配合采样策略或领域自适应方法。

## 4. 消融实验

移除边特征后，QM9 平均 RMSE 上升 12%，证明化学键信息不可忽略。
将求和聚合改为均值聚合后，与分子量强相关的性质预测误差上升明显，
验证了聚合方式的选择应与任务特性匹配。
去掉 GRU 更新改用简单拼接，训练稳定性下降，收敛需要更多轮次。

## 5. 结论

消息传递框架在分子性质预测上效果显著，但收益并非均匀分布于所有任务。
样本量小、类别不平衡、分布偏移的场景仍需针对性处理。
""",
    },
    {
        "name": "知识图谱嵌入用于药物相互作用预测.md",
        "content": """# 知识图谱嵌入用于药物-药物相互作用预测

## 摘要

药物-药物相互作用（DDI）是联合用药安全的核心问题。已有方法多基于
分子结构相似度，难以捕捉药物在生物通路层面的关联。本文构建了一个包含
药物、靶标、酶、通路与不良反应的生物医学知识图谱，并使用知识图谱嵌入
方法进行链接预测，在冷启动场景下优于纯结构方法。

## 1. 动机

基于分子结构的方法假设"结构相似的药物相互作用模式相似"，这一假设在
许多情况下不成立：结构差异很大的药物可能作用于同一通路而产生相互作用。
因此，引入结构化知识（靶标、酶、通路）是对分子结构的必要补充。

## 2. 知识图谱构建

我们从公开生物医学数据库抽取实体与关系，构建包含五类实体
（药物、靶标、酶、通路、不良反应）与六类关系的知识图谱，
共计约 8 万个实体、150 万条三元组。

实体对齐是主要难点：同一药物在不同数据库中标识不同。我们使用
InChIKey 作为药物的统一标识，使用 UniProt ID 对齐蛋白实体，
对齐后实体数量从 12 万缩减至 8 万，消除了大量冗余。

## 3. 方法

对比了三种知识图谱嵌入方法：TransE、DistMult 与 ComplEx。
TransE 将关系建模为翻译操作，适合一对一关系；DistMult 与 ComplEx
通过双线性打分，能更好地处理一对多与多对多关系，这在生物医学图谱中
更为常见。

对于 DDI 预测，我们将任务形式化为链接预测：给定两个药物，
预测它们之间是否存在"相互作用"边，以及相互作用的类型。

为处理冷启动，我们引入了药物描述文本的表示作为补充：对于图谱中
连接稀疏的新药物，用其文本描述的嵌入初始化实体向量，
再参与图谱训练。这一策略在新药子集上效果提升显著。

## 4. 实验

数据集：以 ZINC 中的药物分子为候选集，结合公开 DDI 标注构建正负样本。
评价指标：ROC-AUC、PR-AUC 与 Hits@10。

结果：ComplEx 在整体测试集上 ROC-AUC 达到 0.948，
优于 TransE 的 0.902 与 DistMult 的 0.931，验证了双线性模型对
多对多关系的建模优势。

冷启动子集（训练集中出现次数少于 5 次的药物）上，引入文本初始化后
ROC-AUC 从 0.781 提升至 0.856，提升幅度显著高于整体集合，
说明文本信息有效补偿了结构信息的缺失。

## 5. 讨论

知识图谱方法与分子图方法并非替代关系。两者分别刻画了药物的
"关系视角"与"结构视角"。初步的融合实验显示，将图谱嵌入与
MPNN 得到的分子表示拼接后，ROC-AUC 进一步提升至 0.961，
但融合方式较为朴素，如何设计更合理的交互机制仍是开放问题。

可解释性方面，知识图谱天然具有优势：预测结果可以沿着路径回溯，
给出"药物 A 与药物 B 共同作用于靶标 T"这样的解释，
这比注意力权重更容易被领域专家接受。
""",
    },
]

# ── Preset knowledge graph ───────────────────────────────────────────────────
# Mirrors what kg_extractor would produce from the documents above. Used when no
# LLM key is available so the demo still shows a populated graph.

PRESET_ENTITIES = [
    ("Method", "Graph Neural Network", "图神经网络", "直接在分子图结构上学习的神经网络家族"),
    ("Method", "Message Passing Neural Network", "消息传递神经网络", "将图模型统一为消息传递-聚合-更新三阶段的框架"),
    ("Method", "Graph Convolutional Network", "图卷积网络", "把卷积推广到图结构的邻域聚合方法"),
    ("Method", "Graph Attention Network", "图注意力网络", "用注意力为邻居分配权重的图模型"),
    ("Method", "Knowledge Graph Embedding", "知识图谱嵌入", "把实体与关系映射到低维向量的方法"),
    ("Method", "Morgan Fingerprint", "摩根指纹", "人工设计的分子特征表示基线"),
    ("Method", "Self-supervised Pretraining", "自监督预训练", "在大规模无标注分子上预训练再微调"),
    ("Task", "Molecular Property Prediction", "分子性质预测", "预测溶解度毒性等理化性质"),
    ("Task", "Drug-Drug Interaction Prediction", "药物相互作用预测", "预测联合用药的不良反应"),
    ("Task", "Drug Repositioning", "药物重定位", "为已上市药物寻找新适应症"),
    ("Task", "Link Prediction", "链接预测", "预测知识图谱中缺失的边"),
    ("Dataset", "QM9", "QM9 数据集", "含十三万小分子的量子化学性质数据集"),
    ("Dataset", "MoleculeNet", "MoleculeNet 基准", "涵盖多个分子任务的基准集合"),
    ("Dataset", "ZINC", "ZINC 化合物库", "含数百万化合物的公开库"),
    ("Dataset", "BACE", "BACE 数据集", "小样本分类任务数据集"),
    ("Metric", "RMSE", "均方根误差", "回归任务评价指标"),
    ("Metric", "ROC-AUC", "ROC 曲线下面积", "分类任务评价指标"),
    ("Metric", "Hits@10", "Hits@10", "链接预测排序指标"),
    ("Challenge", "Oversmoothing", "过平滑", "层数加深导致节点表示趋同"),
    ("Challenge", "Interpretability", "可解释性", "需要解释预测依据而非仅给结果"),
    ("Challenge", "Cold Start", "冷启动", "新靶点新化合物缺乏历史数据"),
    ("Domain", "Drug Discovery", "药物发现", "GNN 的主要应用领域"),
    ("Model", "TransE", "TransE", "把关系建模为翻译操作的嵌入模型"),
    ("Model", "ComplEx", "ComplEx", "复数域双线性打分嵌入模型"),
    ("Result", "ROC-AUC 0.948 on DDI", "DDI 预测 ROC-AUC 0.948", "ComplEx 在整体测试集上的结果"),
]

PRESET_TRIPLES = [
    ("Message Passing Neural Network", "EXTENDS", "Graph Neural Network", "MPNN 是 GNN 的统一框架化实现"),
    ("Graph Convolutional Network", "BELONGS_TO", "Graph Neural Network", "GCN 属于 GNN 家族"),
    ("Graph Attention Network", "BELONGS_TO", "Graph Neural Network", "GAT 属于 GNN 家族"),
    ("Graph Attention Network", "USES", "Self-supervised Pretraining", "GAT 常配合预训练使用"),
    ("Graph Neural Network", "USES", "Molecular Property Prediction", "GNN 被用于分子性质预测"),
    ("Graph Neural Network", "USES", "Drug-Drug Interaction Prediction", "GNN 被用于相互作用预测"),
    ("Graph Neural Network", "USES", "Drug Repositioning", "GNN 被用于药物重定位"),
    ("Molecular Property Prediction", "EVALUATED_ON", "QM9", "性质预测在 QM9 上评测"),
    ("Molecular Property Prediction", "EVALUATED_ON", "MoleculeNet", "性质预测在 MoleculeNet 上评测"),
    ("Drug-Drug Interaction Prediction", "EVALUATED_ON", "ZINC", "DDI 预测以 ZINC 为候选集"),
    ("Molecular Property Prediction", "EVALUATED_BY", "RMSE", "回归任务用 RMSE 评价"),
    ("Molecular Property Prediction", "EVALUATED_BY", "ROC-AUC", "分类任务用 ROC-AUC 评价"),
    ("Link Prediction", "EVALUATED_BY", "Hits@10", "链接预测用 Hits@10 评价"),
    ("QM9", "BELONGS_TO", "MoleculeNet", "QM9 属于 MoleculeNet 体系"),
    ("Message Passing Neural Network", "OUTPERFORMS", "Graph Convolutional Network", "MPNN 在多数性质上优于 GCN"),
    ("Message Passing Neural Network", "OUTPERFORMS", "Morgan Fingerprint", "MPNN 优于指纹基线"),
    ("Knowledge Graph Embedding", "USES", "Link Prediction", "图谱嵌入用于链接预测"),
    ("ComplEx", "BELONGS_TO", "Knowledge Graph Embedding", "ComplEx 是一种图谱嵌入"),
    ("TransE", "BELONGS_TO", "Knowledge Graph Embedding", "TransE 是一种图谱嵌入"),
    ("ComplEx", "OUTPERFORMS", "TransE", "ComplEx 在 DDI 上 ROC-AUC 更高"),
    ("ComplEx", "ACHIEVES", "ROC-AUC 0.948 on DDI", "ComplEx 达到 0.948"),
    ("Graph Neural Network", "COMPARED_WITH", "Knowledge Graph Embedding", "两种视角互为补充"),
    ("Graph Neural Network", "USES", "Drug Discovery", "GNN 应用于药物发现领域"),
    ("Graph Neural Network", "PROPOSES", "Oversmoothing", "过平滑是 GNN 的固有挑战"),
    ("Graph Neural Network", "PROPOSES", "Interpretability", "可解释性是待解问题"),
    ("Graph Neural Network", "PROPOSES", "Cold Start", "冷启动是开放挑战"),
    ("BACE", "BELONGS_TO", "MoleculeNet", "BACE 属于 MoleculeNet"),
    ("Self-supervised Pretraining", "USES", "ZINC", "预训练使用 ZINC 大规模分子"),
]

PRESET_COMMUNITY_SUMMARY = (
    "本图谱围绕「图神经网络在药物发现中的应用」组织，可划分为三个社区："
    "（1）分子图方法社区，以 GNN / MPNN / GCN / GAT 为核心，主要服务于分子性质预测任务，"
    "在 QM9 与 MoleculeNet 上以 RMSE、ROC-AUC 评价，并以摩根指纹为基线；"
    "（2）知识图谱方法社区，以 TransE / ComplEx 等嵌入模型为核心，"
    "服务于药物相互作用预测与链接预测，在 ZINC 候选集上以 ROC-AUC / Hits@10 评价；"
    "（3）挑战与方法论社区，涵盖过平滑、可解释性、冷启动三类开放问题，"
    "以及自监督预训练这一缓解数据稀缺的手段。"
    "两个方法社区通过「GNN 与知识图谱嵌入互为补充」这一关系连接，"
    "融合实验显示拼接后 ROC-AUC 从 0.948 提升至 0.961。"
)


def ensure_user(db) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user:
        print(f"[=] 演示账号已存在: {DEMO_EMAIL}")
        return user
    user = User(
        id=str(uuid.uuid4()),
        email=DEMO_EMAIL,
        username=DEMO_USERNAME,
        password_hash=hash_password(DEMO_PASSWORD),
        preferred_model="gpt-4o-mini",
        language="zh",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"[+] 创建演示账号: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return user


def ensure_files(db, user: User):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    created = []
    for doc in SAMPLE_DOCS:
        existing = (
            db.query(File)
            .filter(File.user_id == user.id, File.original_name == doc["name"])
            .first()
        )
        if existing:
            print(f"[=] 文件已存在: {doc['name']}")
            created.append(existing)
            continue

        fid = str(uuid.uuid4())
        stored_name = f"{fid}.md"
        rel_path = os.path.join(settings.UPLOAD_DIR, stored_name)
        raw = doc["content"].encode("utf-8")
        with open(rel_path, "wb") as fh:
            fh.write(raw)

        f = File(
            id=fid,
            user_id=user.id,
            filename=stored_name,
            original_name=doc["name"],
            file_type="md",
            file_size=len(raw),
            storage_path=rel_path,
            data=raw,
        )
        db.add(f)
        created.append(f)
        print(f"[+] 写入文献: {doc['name']} ({len(raw)} bytes)")
    db.commit()
    return created


def build_index(file_ids):
    """Vector-index the sample docs. Skipped gracefully if Chroma is unavailable."""
    try:
        from app.services.rag_service import rag_service
    except Exception as exc:
        print(f"[!] 跳过向量索引（RAG 不可用）: {exc}")
        return
    for fid in file_ids:
        try:
            n = rag_service.index_file_sync(fid)
            print(f"[+] 已建立向量索引: {fid[:8]}… ({n} chunks)")
        except Exception as exc:
            print(f"[!] 索引失败 {fid[:8]}…: {exc}")


def build_graph_preset(user_id: str, file_rows):
    """Write the curated graph so the demo shows a populated KG without an LLM.

    ``file_rows`` is a list of ``(file_id, original_name)`` tuples and ``user_id``
    a plain string rather than ORM objects — the seeding session is already closed
    by this point, and touching a detached instance raises DetachedInstanceError.
    """
    from app.services import kg_store

    entities = [
        {
            "entity_type": etype,
            "name": name,
            "name_zh": name_zh,
            "description": desc,
        }
        for etype, name, name_zh, desc in PRESET_ENTITIES
    ]
    triples = [
        {"relation_type": rel, "source_name": s, "target_name": t, "description": d}
        for rel, s, t, d in PRESET_TRIPLES
    ]

    # Distribute entities across files so per-file badges all look populated.
    # Use ceil (not floor) division so no trailing chunk gets dropped, and clamp
    # to the number of files so every chunk has a home.
    n_files = max(1, len(file_rows))
    per = -(-len(entities) // n_files)
    chunks = [entities[i : i + per] for i in range(0, len(entities), per)]
    for idx, (fid, name) in enumerate(file_rows):
        subset = chunks[idx] if idx < len(chunks) else []
        if not subset:
            continue
        names = {e["name"] for e in subset}
        sub_triples = [
            t
            for t in triples
            if t["source_name"] in names or t["target_name"] in names
        ]
        kg_store.upsert_extraction(user_id, fid, subset, sub_triples)
        print(f"[+] 图谱已写入: {name} ({len(subset)} 实体 / {len(sub_triples)} 关系)")

    # Community summary (single community covering the whole demo graph).
    db = SessionLocal()
    try:
        db.query(KGCommunity).filter(KGCommunity.user_id == user_id).delete(
            synchronize_session=False
        )
        db.add(
            KGCommunity(
                id=str(uuid.uuid4()),
                user_id=user_id,
                community_id=0,
                summary=PRESET_COMMUNITY_SUMMARY,
                entities=[e["name"] for e in entities],
            )
        )
        db.commit()
        print("[+] 社区摘要已写入")
    finally:
        db.close()

    # Mark community id on entities so the graph view groups them.
    db = SessionLocal()
    try:
        db.query(KGEntity).filter(KGEntity.user_id == user_id).update(
            {"community_id": 0}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def build_graph_llm(user_id: str, file_rows):
    """Real extraction via the configured model. Requires an API key."""
    import asyncio

    from app.services import kg_index
    from app.services.llm_service import llm_service

    if not llm_service.has_any_key():
        print("[!] 未检测到任何模型 Key，回退到预置图谱")
        build_graph_preset(user_id, file_rows)
        return

    for fid, name in file_rows:
        try:
            asyncio.run(kg_index.index_file(fid))
            print(f"[+] LLM 抽取完成: {name}")
        except Exception as exc:
            print(f"[!] 抽取失败 {name}: {exc}")


def wipe(user: User, db):
    for f in db.query(File).filter(File.user_id == user.id).all():
        try:
            if f.storage_path and os.path.exists(f.storage_path):
                os.remove(f.storage_path)
        except OSError:
            pass
    db.query(KGTriple).filter(KGTriple.user_id == user.id).delete(synchronize_session=False)
    db.query(KGEntity).filter(KGEntity.user_id == user.id).delete(synchronize_session=False)
    db.query(KGCommunity).filter(KGCommunity.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(File).filter(File.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    print("[x] 已清空演示数据")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true", help="用真实 LLM 抽取图谱")
    ap.add_argument("--reset", action="store_true", help="先清空演示数据再重建")
    ap.add_argument("--no-index", action="store_true", help="跳过向量索引")
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if user and args.reset:
            wipe(user, db)
        user = ensure_user(db)
        files = ensure_files(db, user)
        # Snapshot to plain values before the session closes — ORM objects become
        # detached and raise DetachedInstanceError on attribute access.
        user_id = user.id
        file_rows = [(f.id, f.original_name) for f in files]
    finally:
        db.close()

    if not args.no_index:
        build_index([fid for fid, _ in file_rows])
    else:
        print("[-] 跳过向量索引")

    if args.with_llm:
        build_graph_llm(user_id, file_rows)
    else:
        build_graph_preset(user_id, file_rows)

    db = SessionLocal()
    try:
        n_ent = db.query(KGEntity).filter(KGEntity.user_id == user_id).count()
        n_rel = db.query(KGTriple).filter(KGTriple.user_id == user_id).count()
    finally:
        db.close()

    print()
    print("=" * 56)
    print("  演示账号就绪")
    print(f"  登录: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  文献: {len(file_rows)} 篇")
    print(f"  图谱: {n_ent} 实体 / {n_rel} 关系")
    print("=" * 56)


if __name__ == "__main__":
    main()
