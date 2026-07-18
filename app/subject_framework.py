"""
希沃智教π 跨学科统一知识归因框架 (Phase 2 - 7.2.5)

核心功能：
1. 通用化DAG框架，当前仅数学 -> 支持多学科
2. 统一DecayPropagate、双通道映射、多模态批改底层逻辑
3. 新增学科仅补充对应课标图谱与题型路由规则
4. 快速拓展英语、物理

设计思路：
- 学科注册表（SUBJECT_REGISTRY）：每个学科声明知识图谱类、图谱数据、题型列表、错因标签
- SubjectService：统一归因服务，根据学科获取对应配置与知识图谱实例
- 新增学科只需：1) 添加图谱数据 2) 在注册表新增一条记录
"""
import logging

from app.knowledge_graph import KnowledgeGraph, MATH_KNOWLEDGE_GRAPH
from app.writing_graph import WritingKnowledgeGraph, WRITING_KNOWLEDGE_GRAPH

logger = logging.getLogger(__name__)


# ===== 英语简略知识图谱（2层，演示用） =====

ENGLISH_KNOWLEDGE_GRAPH = {
    "id": "root",
    "name": "初中英语",
    "parent_id": None,
    "level": 0,
    "keywords": ["英语"],
    "prerequisites": [],
    "children": [
        {
            "id": "en_vocab",
            "name": "词汇",
            "parent_id": "root",
            "level": 1,
            "keywords": ["词汇", "单词", "拼写", "词义"],
            "prerequisites": [],
            "children": [
                {"id": "en_vocab_core", "name": "核心词汇", "parent_id": "en_vocab", "level": 2,
                 "keywords": ["核心词汇", "基础单词", "高频词"], "prerequisites": [], "children": []},
                {"id": "en_vocab_expand", "name": "拓展词汇", "parent_id": "en_vocab", "level": 2,
                 "keywords": ["拓展词汇", "高级词汇", "同义词", "反义词"], "prerequisites": ["en_vocab_core"], "children": []},
            ],
        },
        {
            "id": "en_grammar",
            "name": "语法",
            "parent_id": "root",
            "level": 1,
            "keywords": ["语法", "句法", "词法", "时态", "从句"],
            "prerequisites": ["en_vocab"],
            "children": [
                {"id": "en_grammar_tense", "name": "时态", "parent_id": "en_grammar", "level": 2,
                 "keywords": ["时态", "现在时", "过去时", "将来时", "完成时", "进行时"], "prerequisites": [], "children": []},
                {"id": "en_grammar_clause", "name": "从句", "parent_id": "en_grammar", "level": 2,
                 "keywords": ["从句", "定语从句", "状语从句", "宾语从句"], "prerequisites": ["en_grammar_tense"], "children": []},
            ],
        },
        {
            "id": "en_reading",
            "name": "阅读理解",
            "parent_id": "root",
            "level": 1,
            "keywords": ["阅读", "理解", "文章", "主旨", "细节"],
            "prerequisites": ["en_vocab", "en_grammar"],
            "children": [
                {"id": "en_reading_detail", "name": "细节理解", "parent_id": "en_reading", "level": 2,
                 "keywords": ["细节", "事实", "查找", "定位"], "prerequisites": [], "children": []},
                {"id": "en_reading_infer", "name": "推理判断", "parent_id": "en_reading", "level": 2,
                 "keywords": ["推理", "判断", "推断", "言外之意"], "prerequisites": ["en_reading_detail"], "children": []},
            ],
        },
        {
            "id": "en_writing",
            "name": "写作",
            "parent_id": "root",
            "level": 1,
            "keywords": ["写作", "作文", "书面表达", "翻译"],
            "prerequisites": ["en_vocab", "en_grammar", "en_reading"],
            "children": [
                {"id": "en_writing_sentence", "name": "句子表达", "parent_id": "en_writing", "level": 2,
                 "keywords": ["句子", "造句", "句型", "翻译"], "prerequisites": [], "children": []},
                {"id": "en_writing_paragraph", "name": "篇章组织", "parent_id": "en_writing", "level": 2,
                 "keywords": ["篇章", "段落", "衔接", "连贯", "结构"], "prerequisites": ["en_writing_sentence"], "children": []},
            ],
        },
    ],
}


# ===== 物理简略知识图谱（2层，演示用） =====

PHYSICS_KNOWLEDGE_GRAPH = {
    "id": "root",
    "name": "初中物理",
    "parent_id": None,
    "level": 0,
    "keywords": ["物理"],
    "prerequisites": [],
    "children": [
        {
            "id": "ph_mechanics",
            "name": "力学",
            "parent_id": "root",
            "level": 1,
            "keywords": ["力", "运动", "质量", "密度", "压强", "浮力"],
            "prerequisites": [],
            "children": [
                {"id": "ph_mech_motion", "name": "运动与力", "parent_id": "ph_mechanics", "level": 2,
                 "keywords": ["速度", "加速度", "牛顿", "惯性", "平衡力", "摩擦力"], "prerequisites": [], "children": []},
                {"id": "ph_mech_pressure", "name": "压强与浮力", "parent_id": "ph_mechanics", "level": 2,
                 "keywords": ["压强", "液体压强", "大气压", "浮力", "阿基米德"], "prerequisites": ["ph_mech_motion"], "children": []},
            ],
        },
        {
            "id": "ph_electricity",
            "name": "电学",
            "parent_id": "root",
            "level": 1,
            "keywords": ["电", "电路", "电流", "电压", "电阻", "功率"],
            "prerequisites": [],
            "children": [
                {"id": "ph_elec_circuit", "name": "电路基础", "parent_id": "ph_electricity", "level": 2,
                 "keywords": ["电路", "串联", "并联", "欧姆定律", "电流表", "电压表"], "prerequisites": [], "children": []},
                {"id": "ph_elec_power", "name": "电功与电功率", "parent_id": "ph_electricity", "level": 2,
                 "keywords": ["电功", "电功率", "焦耳定律", "电能", "额定功率"], "prerequisites": ["ph_elec_circuit"], "children": []},
            ],
        },
        {
            "id": "ph_optics",
            "name": "光学",
            "parent_id": "root",
            "level": 1,
            "keywords": ["光", "反射", "折射", "透镜", "成像"],
            "prerequisites": [],
            "children": [
                {"id": "ph_opt_reflect", "name": "光的反射", "parent_id": "ph_optics", "level": 2,
                 "keywords": ["反射", "入射角", "反射角", "镜面", "漫反射"], "prerequisites": [], "children": []},
                {"id": "ph_opt_lens", "name": "透镜与成像", "parent_id": "ph_optics", "level": 2,
                 "keywords": ["透镜", "凸透镜", "凹透镜", "焦点", "实像", "虚像"], "prerequisites": ["ph_opt_reflect"], "children": []},
            ],
        },
        {
            "id": "ph_thermal",
            "name": "热学",
            "parent_id": "root",
            "level": 1,
            "keywords": ["热", "温度", "物态变化", "比热容", "内能"],
            "prerequisites": [],
            "children": [
                {"id": "ph_thermal_state", "name": "物态变化", "parent_id": "ph_thermal", "level": 2,
                 "keywords": ["熔化", "凝固", "汽化", "液化", "升华", "凝华"], "prerequisites": [], "children": []},
                {"id": "ph_thermal_energy", "name": "内能与热量", "parent_id": "ph_thermal", "level": 2,
                 "keywords": ["内能", "热量", "比热容", "热机", "热值"], "prerequisites": ["ph_thermal_state"], "children": []},
            ],
        },
    ],
}


# ===== 学科注册表 =====

SUBJECT_REGISTRY: dict[str, dict] = {
    "math": {
        "name": "数学",
        "knowledge_graph_class": KnowledgeGraph,
        "knowledge_graph_data": MATH_KNOWLEDGE_GRAPH,
        "question_types": ["calculation", "proof", "geometry", "application"],
        "grading_model": "standard",
        "error_cause_labels": ["计算粗心", "概念混淆", "审题不清", "辅助线缺失", "逻辑跳步", "知识缺失"],
    },
    "chinese": {
        "name": "语文",
        "knowledge_graph_class": WritingKnowledgeGraph,
        "knowledge_graph_data": WRITING_KNOWLEDGE_GRAPH,
        "question_types": ["essay", "reading", "vocabulary"],
        "grading_model": "standard",
        "error_cause_labels": ["素材匮乏", "逻辑断层", "修辞单一", "偏题跑题", "书写潦草"],
    },
    "english": {
        "name": "英语",
        "knowledge_graph_class": KnowledgeGraph,
        "knowledge_graph_data": ENGLISH_KNOWLEDGE_GRAPH,
        "question_types": ["vocabulary", "grammar", "reading", "writing"],
        "grading_model": "standard",
        "error_cause_labels": ["词汇错误", "语法错误", "理解偏差", "拼写错误"],
    },
    "physics": {
        "name": "物理",
        "knowledge_graph_class": KnowledgeGraph,
        "knowledge_graph_data": PHYSICS_KNOWLEDGE_GRAPH,
        "question_types": ["calculation", "experiment", "proof", "application"],
        "grading_model": "standard",
        "error_cause_labels": ["概念混淆", "公式记错", "单位换算", "实验操作", "逻辑跳步"],
    },
}


class SubjectService:
    """跨学科统一归因服务

    提供统一的学科配置获取、知识图谱实例化、学科列表查询接口。
    新增学科只需在 SUBJECT_REGISTRY 中添加一条记录即可。
    """

    # 缓存已创建的知识图谱实例（避免重复构建）
    _kg_cache: dict[str, KnowledgeGraph] = {}

    @staticmethod
    def get_subject(subject: str) -> dict:
        """获取学科配置

        Args:
            subject: 学科标识，如 "math"、"english"、"physics"

        Returns:
            dict: 学科配置信息，包含 name/knowledge_graph_class/knowledge_graph_data 等。
                  若学科不存在，默认返回数学配置。
        """
        return SUBJECT_REGISTRY.get(subject, SUBJECT_REGISTRY["math"])

    @staticmethod
    def get_knowledge_graph(subject: str) -> KnowledgeGraph:
        """获取学科对应的知识图谱实例（带缓存）

        Args:
            subject: 学科标识

        Returns:
            KnowledgeGraph: 知识图谱实例（已预计算）
        """
        if subject in SubjectService._kg_cache:
            return SubjectService._kg_cache[subject]

        config = SubjectService.get_subject(subject)
        kg_class = config["knowledge_graph_class"]
        kg_data = config["knowledge_graph_data"]
        kg = kg_class(kg_data)
        kg.precompute()

        SubjectService._kg_cache[subject] = kg
        logger.info(f"[SubjectService] 知识图谱已缓存: subject={subject}, nodes={len(kg.get_all_nodes())}")
        return kg

    @staticmethod
    def list_subjects() -> list[dict]:
        """列出所有已注册学科

        Returns:
            list[dict]: 学科列表，每项包含 id/name/question_types/error_cause_labels
        """
        return [
            {
                "id": k,
                "name": v["name"],
                "question_types": v["question_types"],
                "error_cause_labels": v["error_cause_labels"],
            }
            for k, v in SUBJECT_REGISTRY.items()
        ]

    @staticmethod
    def get_error_cause_labels(subject: str) -> list[str]:
        """获取学科对应的错因标签列表

        Args:
            subject: 学科标识

        Returns:
            list[str]: 错因标签列表
        """
        config = SubjectService.get_subject(subject)
        return config.get("error_cause_labels", [])

    @staticmethod
    def get_question_types(subject: str) -> list[str]:
        """获取学科对应的题型列表

        Args:
            subject: 学科标识

        Returns:
            list[str]: 题型列表
        """
        config = SubjectService.get_subject(subject)
        return config.get("question_types", [])

    @staticmethod
    def clear_cache():
        """清空知识图谱缓存（用于测试或配置更新后重载）"""
        SubjectService._kg_cache.clear()
        logger.info("[SubjectService] 知识图谱缓存已清空")
