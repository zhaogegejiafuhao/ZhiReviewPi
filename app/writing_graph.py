"""
希沃智教π 写作能力DAG图谱 - 作文分层归因支撑

数据结构：与 knowledge_graph.py 中 MATH_KNOWLEDGE_GRAPH 同构的树形JSON，
每个节点包含：
  - id: 唯一标识
  - name: 知识点名称
  - parent_id: 父节点ID
  - level: 层级（0=根, 1=维度, 2=子能力, 3=具体技能）
  - keywords: 关键词列表（用于错因标签映射）
  - prerequisites: 前置依赖知识点ID列表（用于DecayPropagate后向传播）
"""
from app.knowledge_graph import KnowledgeGraph


# 写作能力DAG图谱
WRITING_KNOWLEDGE_GRAPH = {
    "id": "root",
    "name": "写作能力图谱",
    "parent_id": None,
    "level": 0,
    "keywords": [],
    "prerequisites": [],
    "children": [
        {
            "id": "theme",
            "name": "审题立意",
            "parent_id": "root",
            "level": 1,
            "keywords": ["审题", "立意", "主题", "论点", "观点", "偏题", "跑题"],
            "prerequisites": [],
            "children": [
                {
                    "id": "topic_understanding",
                    "name": "话题理解",
                    "parent_id": "theme",
                    "level": 2,
                    "keywords": ["话题", "理解", "题意", "素材", "素材匮乏"],
                    "prerequisites": [],
                    "children": [],
                },
                {
                    "id": "thesis_extraction",
                    "name": "论点提炼",
                    "parent_id": "theme",
                    "level": 2,
                    "keywords": ["论点", "提炼", "中心思想", "主旨", "偏题跑题"],
                    "prerequisites": ["topic_understanding"],
                    "children": [],
                },
                {
                    "id": "theme_depth",
                    "name": "立意深度",
                    "parent_id": "theme",
                    "level": 2,
                    "keywords": ["深度", "立意", "思想", "升华", "内涵", "素材匮乏"],
                    "prerequisites": ["thesis_extraction"],
                    "children": [],
                },
            ],
        },
        {
            "id": "structure",
            "name": "结构组织",
            "parent_id": "root",
            "level": 1,
            "keywords": ["结构", "组织", "段落", "过渡", "逻辑"],
            "prerequisites": ["theme"],
            "children": [
                {
                    "id": "opening",
                    "name": "开头引入",
                    "parent_id": "structure",
                    "level": 2,
                    "keywords": ["开头", "引入", "破题", "起笔", "逻辑断层"],
                    "prerequisites": ["thesis_extraction"],
                    "children": [],
                },
                {
                    "id": "paragraph_transition",
                    "name": "段落过渡",
                    "parent_id": "structure",
                    "level": 2,
                    "keywords": ["过渡", "衔接", "逻辑", "连贯", "逻辑断层"],
                    "prerequisites": ["opening"],
                    "children": [],
                },
                {
                    "id": "ending",
                    "name": "结尾升华",
                    "parent_id": "structure",
                    "level": 2,
                    "keywords": ["结尾", "升华", "收束", "总结", "逻辑断层"],
                    "prerequisites": ["paragraph_transition"],
                    "children": [],
                },
            ],
        },
        {
            "id": "expression",
            "name": "语言表达",
            "parent_id": "root",
            "level": 1,
            "keywords": ["语言", "表达", "词汇", "修辞", "句式"],
            "prerequisites": ["structure"],
            "children": [
                {
                    "id": "vocabulary",
                    "name": "词汇丰富度",
                    "parent_id": "expression",
                    "level": 2,
                    "keywords": ["词汇", "丰富", "用词", "词语", "修辞单一"],
                    "prerequisites": [],
                    "children": [],
                },
                {
                    "id": "rhetoric",
                    "name": "修辞运用",
                    "parent_id": "expression",
                    "level": 2,
                    "keywords": ["修辞", "比喻", "拟人", "排比", "夸张", "修辞单一"],
                    "prerequisites": ["vocabulary"],
                    "children": [],
                },
                {
                    "id": "sentence_variety",
                    "name": "句式变化",
                    "parent_id": "expression",
                    "level": 2,
                    "keywords": ["句式", "变化", "长短句", "整散句", "修辞单一"],
                    "prerequisites": ["vocabulary"],
                    "children": [],
                },
            ],
        },
        {
            "id": "writing_norm",
            "name": "书写规范",
            "parent_id": "root",
            "level": 1,
            "keywords": ["书写", "规范", "字迹", "卷面", "潦草"],
            "prerequisites": [],
            "children": [
                {
                    "id": "handwriting",
                    "name": "字迹工整度",
                    "parent_id": "writing_norm",
                    "level": 2,
                    "keywords": ["字迹", "工整", "书写", "潦草", "书写潦草"],
                    "prerequisites": [],
                    "children": [],
                },
                {
                    "id": "page_neatness",
                    "name": "卷面整洁度",
                    "parent_id": "writing_norm",
                    "level": 2,
                    "keywords": ["卷面", "整洁", "涂改", "书写潦草"],
                    "prerequisites": ["handwriting"],
                    "children": [],
                },
            ],
        },
    ],
}

# 写作错因标签 -> DAG一级维度映射
WRITING_ERROR_CAUSE_MAPPING: dict[str, str] = {
    "素材匮乏": "theme",
    "逻辑断层": "structure",
    "修辞单一": "expression",
    "偏题跑题": "theme",
    "书写潦草": "writing_norm",
}

# 写作错因标签 -> DAG二级/三级节点映射（更细粒度）
WRITING_ERROR_CAUSE_FINE_MAPPING: dict[str, list[str]] = {
    "素材匮乏": ["topic_understanding", "theme_depth"],
    "逻辑断层": ["opening", "paragraph_transition", "ending"],
    "修辞单一": ["vocabulary", "rhetoric", "sentence_variety"],
    "偏题跑题": ["topic_understanding", "thesis_extraction"],
    "书写潦草": ["handwriting", "page_neatness"],
}

# 写作错因标签 -> 改进建议模板
WRITING_ERROR_SUGGESTIONS: dict[str, str] = {
    "素材匮乏": "建议加强素材积累，多阅读优秀范文和时评文章，建立个人素材库，按主题分类整理名言警句、典型事例",
    "逻辑断层": "建议练习段落间过渡句的写法，使用'首先/其次/最后'、'不仅如此'、'更重要的是'等逻辑衔接词，确保文章脉络清晰",
    "修辞单一": "建议系统学习常见修辞手法（比喻、拟人、排比、夸张、对偶等），在写作中有意识地运用2-3种修辞，丰富语言表现力",
    "偏题跑题": "建议审题时圈画关键词，先列提纲再动笔，每写完一段回看是否围绕中心论点展开",
    "书写潦草": "建议每天练习15分钟硬笔字帖，书写时注意字距行距，减少涂改，保持卷面整洁",
}


class WritingKnowledgeGraph(KnowledgeGraph):
    """
    写作能力DAG图谱服务

    复用 KnowledgeGraph 的全部结构与方法（展平、祖先查询、深度计算、
    关键词匹配、雷达维度等），仅替换底层数据为 WRITING_KNOWLEDGE_GRAPH。
    """

    def __init__(self, graph_data: dict | None = None):
        super().__init__(graph_data or WRITING_KNOWLEDGE_GRAPH)

    @staticmethod
    def map_error_cause_to_nodes(error_cause: str) -> list[str]:
        """
        将写作错因标签映射到DAG图谱中的具体节点ID列表

        Args:
            error_cause: 写作错因标签，如 "素材匮乏"、"逻辑断层" 等

        Returns:
            匹配的节点ID列表
        """
        return WRITING_ERROR_CAUSE_FINE_MAPPING.get(error_cause, [])

    @staticmethod
    def map_error_cause_to_dimension(error_cause: str) -> str | None:
        """
        将写作错因标签映射到DAG一级维度节点ID

        Args:
            error_cause: 写作错因标签

        Returns:
            一级维度节点ID，如 "theme"、"structure" 等
        """
        return WRITING_ERROR_CAUSE_MAPPING.get(error_cause)

    @staticmethod
    def get_error_cause_suggestion(error_cause: str) -> str:
        """
        获取写作错因标签对应的改进建议

        Args:
            error_cause: 写作错因标签

        Returns:
            改进建议文本
        """
        return WRITING_ERROR_SUGGESTIONS.get(error_cause, "建议加强写作练习，多阅读优秀范文")

    def get_writing_radar_dimensions(self) -> list[dict]:
        """
        获取写作能力雷达图的一级维度（审题立意、结构组织、语言表达、书写规范）

        Returns:
            维度列表，每项包含 id 和 name
        """
        return self.get_radar_dimensions()
