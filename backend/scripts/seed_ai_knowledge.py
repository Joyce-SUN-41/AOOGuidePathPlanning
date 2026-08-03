"""人工智能通识课 — 知识点种子数据生成器

依据《人工智能导论》课程 PPT（911 页），构建完整的知识点层级体系：
每讲 → 模块 → 概念 → 前置依赖

运行方式:
    cd backend && python scripts/seed_ai_knowledge.py

需要数据库连接正常。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_graph import KnowledgeGraphEdge


# ── 课程知识点体系 ──────────────────────────────────────

AI_COURSE_KP = [
    # ====== 第一讲: 认识人工智能 ======
    {
        "id": "kp_ai_intro",
        "name": "认识人工智能",
        "description": "人工智能的定义、本质属性和内在逻辑",
        "subject": "人工智能导论",
        "difficulty_level": 1,
        "layer": "第一讲",
        "children": [
            {
                "id": "kp_ai_definition",
                "name": "AI的定义与本质",
                "description": "Artificial Intelligence：人造的学习、判断、理解等能力，能力是AI最本质的属性",
                "difficulty": 1,
                "prerequisites": [],
            },
            {
                "id": "kp_ai_history",
                "name": "AI发展史",
                "description": "两起两落：1956达特茅斯会议→1970s第一次寒冬→1980s专家系统→1990s第二次寒冬→2000s深度学习→2020s大模型时代",
                "difficulty": 1,
                "prerequisites": [],
            },
            {
                "id": "kp_ai_pioneers",
                "name": "AI奠基人物",
                "description": "图灵(图灵机/图灵测试)、乔姆斯基(计算语言学)、吴文俊(数学机械化)、辛顿(深度学习)",
                "difficulty": 1,
                "prerequisites": [],
            },
            {
                "id": "kp_ai_logic",
                "name": "AI能力的内在逻辑",
                "description": "记忆→计算→学习→判别→决策的五阶段能力链条",
                "difficulty": 2,
                "prerequisites": ["kp_ai_definition"],
            },
        ],
    },
    # ====== 第二讲: 机器学习基础 ======
    {
        "id": "kp_ml_basics",
        "name": "机器学习基础",
        "description": "机器学习的核心思想、分类与基本方法",
        "subject": "人工智能导论",
        "difficulty_level": 2,
        "layer": "第二讲",
        "children": [
            {
                "id": "kp_ml_concept",
                "name": "机器学习概念",
                "description": "从数据中学习规律，三大范式：监督学习、无监督学习、强化学习",
                "difficulty": 1,
                "prerequisites": ["kp_ai_definition"],
            },
            {
                "id": "kp_supervised_learning",
                "name": "监督学习",
                "description": "分类与回归：KNN、决策树、SVM、线性回归、逻辑回归",
                "difficulty": 2,
                "prerequisites": ["kp_ml_concept"],
            },
            {
                "id": "kp_unsupervised_learning",
                "name": "无监督学习",
                "description": "聚类(K-means)、降维(PCA)、关联规则、异常检测",
                "difficulty": 2,
                "prerequisites": ["kp_ml_concept"],
            },
            {
                "id": "kp_overfitting",
                "name": "过拟合与正则化",
                "description": "偏差-方差权衡、L1/L2正则化、交叉验证、早停法",
                "difficulty": 3,
                "prerequisites": ["kp_supervised_learning"],
            },
            {
                "id": "kp_model_evaluation",
                "name": "模型评估",
                "description": "准确率/精确率/召回率/F1、ROC/AUC、混淆矩阵",
                "difficulty": 2,
                "prerequisites": ["kp_supervised_learning"],
            },
        ],
    },
    # ====== 第三讲: 深度学习 ======
    {
        "id": "kp_deep_learning",
        "name": "深度学习",
        "description": "神经网络基础、CNN、RNN、训练技巧",
        "subject": "人工智能导论",
        "difficulty_level": 3,
        "layer": "第三讲",
        "children": [
            {
                "id": "kp_neural_network",
                "name": "神经网络基础",
                "description": "感知机、多层感知机(MLP)、激活函数(ReLU/Sigmoid/Tanh)、反向传播",
                "difficulty": 2,
                "prerequisites": ["kp_ml_concept"],
            },
            {
                "id": "kp_cnn",
                "name": "卷积神经网络(CNN)",
                "description": "卷积层、池化层、经典架构(LeNet/AlexNet/VGG/ResNet)",
                "difficulty": 3,
                "prerequisites": ["kp_neural_network"],
            },
            {
                "id": "kp_rnn",
                "name": "循环神经网络(RNN)",
                "description": "RNN/LSTM/GRU、序列建模、梯度消失与爆炸",
                "difficulty": 3,
                "prerequisites": ["kp_neural_network"],
            },
            {
                "id": "kp_training_techniques",
                "name": "深度学习训练技巧",
                "description": "Batch Normalization、Dropout、学习率调度、迁移学习",
                "difficulty": 3,
                "prerequisites": ["kp_neural_network", "kp_overfitting"],
            },
        ],
    },
    # ====== 第四讲: 计算机视觉 ======
    {
        "id": "kp_computer_vision",
        "name": "计算机视觉",
        "description": "图像处理、目标检测、图像分割、生成模型",
        "subject": "人工智能导论",
        "difficulty_level": 3,
        "layer": "第四讲",
        "children": [
            {
                "id": "kp_image_processing",
                "name": "图像处理基础",
                "description": "颜色空间、滤波、边缘检测、特征提取(SIFT/HOG)",
                "difficulty": 2,
                "prerequisites": ["kp_cnn"],
            },
            {
                "id": "kp_object_detection",
                "name": "目标检测",
                "description": "R-CNN系列、YOLO、SSD、Anchor机制、NMS",
                "difficulty": 4,
                "prerequisites": ["kp_cnn", "kp_image_processing"],
            },
            {
                "id": "kp_image_segmentation",
                "name": "图像分割",
                "description": "语义分割(FCN/U-Net)、实例分割(Mask R-CNN)",
                "difficulty": 4,
                "prerequisites": ["kp_cnn"],
            },
            {
                "id": "kp_image_generation",
                "name": "图像生成",
                "description": "GAN、VAE、扩散模型(Diffusion)、Stable Diffusion原理",
                "difficulty": 4,
                "prerequisites": ["kp_neural_network"],
            },
        ],
    },
    # ====== 第五讲: 自然语言处理 ======
    {
        "id": "kp_nlp",
        "name": "自然语言处理",
        "description": "文本处理、词向量、注意力机制、大语言模型",
        "subject": "人工智能导论",
        "difficulty_level": 3,
        "layer": "第五讲",
        "children": [
            {
                "id": "kp_text_processing",
                "name": "文本预处理",
                "description": "分词、词性标注、命名实体识别(NER)、TF-IDF",
                "difficulty": 2,
                "prerequisites": ["kp_ml_concept"],
            },
            {
                "id": "kp_word_embeddings",
                "name": "词向量与语言模型",
                "description": "Word2Vec、GloVe、ELMo、语言模型基础",
                "difficulty": 3,
                "prerequisites": ["kp_text_processing"],
            },
            {
                "id": "kp_transformer",
                "name": "Transformer架构",
                "description": "Self-Attention、Multi-Head Attention、位置编码、Encoder-Decoder",
                "difficulty": 4,
                "prerequisites": ["kp_neural_network", "kp_word_embeddings"],
            },
            {
                "id": "kp_llm",
                "name": "大语言模型(LLM)",
                "description": "GPT系列、BERT、预训练+微调范式、Prompt Engineering、RLHF",
                "difficulty": 4,
                "prerequisites": ["kp_transformer"],
            },
        ],
    },
    # ====== 第六讲: 知识图谱 ======
    {
        "id": "kp_knowledge_graph",
        "name": "知识图谱",
        "description": "知识表示、知识抽取、知识推理与问答",
        "subject": "人工智能导论",
        "difficulty_level": 3,
        "layer": "第六讲",
        "children": [
            {
                "id": "kp_knowledge_representation",
                "name": "知识表示",
                "description": "RDF/OWL、属性图、实体-关系建模、知识图谱存储",
                "difficulty": 3,
                "prerequisites": ["kp_ai_definition"],
            },
            {
                "id": "kp_knowledge_extraction",
                "name": "知识抽取",
                "description": "实体识别、关系抽取、事件抽取、知识融合",
                "difficulty": 3,
                "prerequisites": ["kp_text_processing", "kp_knowledge_representation"],
            },
            {
                "id": "kp_knowledge_reasoning",
                "name": "知识推理",
                "description": "规则推理、图神经网络推理、知识图谱补全",
                "difficulty": 4,
                "prerequisites": ["kp_knowledge_representation", "kp_neural_network"],
            },
        ],
    },
    # ====== 第七讲: AI伦理与安全 ======
    {
        "id": "kp_ai_ethics",
        "name": "AI伦理与安全",
        "description": "AI伦理原则、算法公平性、可解释AI、安全对齐",
        "subject": "人工智能导论",
        "difficulty_level": 2,
        "layer": "第七讲",
        "children": [
            {
                "id": "kp_ai_ethics_principles",
                "name": "AI伦理原则",
                "description": "公平性、透明性、可问责性、隐私保护、人本AI",
                "difficulty": 1,
                "prerequisites": ["kp_ai_definition"],
            },
            {
                "id": "kp_algorithmic_fairness",
                "name": "算法公平性",
                "description": "数据偏见、模型偏见检测与缓解、公平性指标",
                "difficulty": 3,
                "prerequisites": ["kp_ml_concept", "kp_ai_ethics_principles"],
            },
            {
                "id": "kp_explainable_ai",
                "name": "可解释AI (XAI)",
                "description": "LIME、SHAP、Grad-CAM、注意力可视化、决策树解释",
                "difficulty": 3,
                "prerequisites": ["kp_ml_concept", "kp_ai_ethics_principles"],
            },
            {
                "id": "kp_ai_safety",
                "name": "AI安全与对齐",
                "description": "对抗攻击与防御、价值对齐(Alignment)、RLHF安全训练",
                "difficulty": 4,
                "prerequisites": ["kp_llm", "kp_ai_ethics_principles"],
            },
        ],
    },
    # ====== 第八讲: AI前沿与应用 ======
    {
        "id": "kp_ai_frontier",
        "name": "AI前沿与应用",
        "description": "多模态AI、具身智能、自动驾驶、AI Agent",
        "subject": "人工智能导论",
        "difficulty_level": 3,
        "layer": "第八讲",
        "children": [
            {
                "id": "kp_multimodal_ai",
                "name": "多模态AI",
                "description": "图文理解(CLIP/BLIP)、文生图(DALL-E/SD)、文生视频(Sora)、多模态大模型",
                "difficulty": 4,
                "prerequisites": ["kp_transformer", "kp_image_generation"],
            },
            {
                "id": "kp_embodied_ai",
                "name": "具身智能与机器人",
                "description": "感知-规划-控制闭环、强化学习与机器人、Sim-to-Real",
                "difficulty": 4,
                "prerequisites": ["kp_computer_vision", "kp_neural_network"],
            },
            {
                "id": "kp_autonomous_driving",
                "name": "自动驾驶技术",
                "description": "感知(激光雷达/视觉)、规划、控制、端到端驾驶",
                "difficulty": 4,
                "prerequisites": ["kp_computer_vision", "kp_object_detection"],
            },
            {
                "id": "kp_ai_agent",
                "name": "AI Agent",
                "description": "LLM Agent架构、工具调用(Function Calling)、多Agent协作、AutoGPT/MetaGPT",
                "difficulty": 4,
                "prerequisites": ["kp_llm"],
            },
            {
                "id": "kp_federated_learning",
                "name": "联邦学习",
                "description": "隐私保护机器学习、横向/纵向联邦、安全聚合",
                "difficulty": 4,
                "prerequisites": ["kp_ml_concept", "kp_ai_ethics_principles"],
            },
        ],
    },
]

# ── 知识图谱边（课程章节间的学习顺序） ─────────────────

COURSE_GRAPH_EDGES = [
    # 基础知识链路
    ("kp_ai_intro", "kp_ml_basics", "prerequisite"),     # AI认知 → 机器学习
    ("kp_ml_basics", "kp_deep_learning", "prerequisite"),  # ML → 深度学习
    ("kp_ai_intro", "kp_ai_ethics", "prerequisite"),     # AI认知 → 伦理
    ("kp_ai_intro", "kp_knowledge_graph", "prerequisite"), # AI认知 → 知识图谱

    # 深度学习 → 各应用方向
    ("kp_deep_learning", "kp_computer_vision", "prerequisite"),  # DL → CV
    ("kp_deep_learning", "kp_nlp", "prerequisite"),              # DL → NLP
    ("kp_deep_learning", "kp_ai_frontier", "prerequisite"),      # DL → 前沿

    # CV → 自动驾驶
    ("kp_computer_vision", "kp_autonomous_driving", "prerequisite"),

    # NLP → 知识抽取
    ("kp_nlp", "kp_knowledge_extraction", "related"),

    # LLM → AI Agent
    ("kp_llm", "kp_ai_agent", "prerequisite"),

    # 伦理 → 安全
    ("kp_ai_ethics", "kp_ai_safety", "prerequisite"),
]


async def seed_knowledge_points():
    """将 AI 课程知识点写入数据库"""
    async with AsyncSessionLocal() as db:
        # 检查是否已有数据
        result = await db.execute(select(KnowledgePoint).limit(1))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"[seed] 知识点表已有数据 (如 {existing.name})，跳过种子数据")
            # 询问是否强制覆盖
            return

        created = 0
        kp_map = {}  # id → KnowledgePoint instance

        for module in AI_COURSE_KP:
            # 创建模块级知识点
            kp = KnowledgePoint(
                name=module["name"],
                description=module.get("description", ""),
                subject=module["subject"],
                difficulty_level=module["difficulty_level"],
                layer=module.get("layer", ""),
                tags=["AI通识", "人工智能导论", module.get("layer", "")],
            )
            # 使用自定义 ID（如果数据库支持 UUID 字符串）
            db.add(kp)
            await db.flush()
            kp_map[module["id"]] = kp
            created += 1

            # 创建子知识点
            for child in module["children"]:
                child_kp = KnowledgePoint(
                    name=child["name"],
                    description=child.get("description", ""),
                    subject=module["subject"],
                    difficulty_level=child["difficulty"],
                    layer=module.get("layer", ""),
                    parent_id=kp.id,
                    tags=["AI通识", "人工智能导论", module.get("layer", "")],
                )
                db.add(child_kp)
                await db.flush()
                kp_map[child["id"]] = child_kp
                created += 1

        await db.commit()
        print(f"[seed] 已创建 {created} 个知识点")

        # 创建知识图谱边
        edge_count = 0
        for source_id, target_id, rel_type in COURSE_GRAPH_EDGES:
            src = kp_map.get(source_id)
            tgt = kp_map.get(target_id)
            if src and tgt:
                edge = KnowledgeGraphEdge(
                    source_kp_id=src.id,
                    target_kp_id=tgt.id,
                    relation_type=rel_type,
                )
                db.add(edge)
                edge_count += 1

        await db.commit()
        print(f"[seed] 已创建 {edge_count} 条知识图谱边")


async def main():
    print("=" * 50)
    print("AI 通识课知识点种子数据生成")
    print("=" * 50)

    # 检查数据库连接
    try:
        from app.core.database import check_db_connection
        ok = await check_db_connection()
        if not ok:
            print("[seed] 数据库连接失败，请确认 PostgreSQL 已启动")
            return
    except Exception as e:
        print(f"[seed] 数据库连接异常: {e}")
        return

    await seed_knowledge_points()
    print("[seed] 完成！")


if __name__ == "__main__":
    asyncio.run(main())
