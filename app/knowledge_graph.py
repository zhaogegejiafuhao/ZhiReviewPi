"""
希沃智教π 课标知识图谱 - 基于义务教育数学课程标准（2022年版）初中部分

数据结构：树形JSON，每个节点包含：
  - id: 唯一标识
  - name: 知识点名称
  - parent_id: 父节点ID
  - level: 层级（0=根, 1=模块, 2=章节, 3=知识点）
  - keywords: 关键词列表（用于错题映射的关键词规则通道）
  - prerequisites: 前置依赖知识点ID列表（用于DecayPropagate后向传播）
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 初中数学知识图谱
MATH_KNOWLEDGE_GRAPH = {
    "id": "root",
    "name": "初中数学",
    "parent_id": None,
    "level": 0,
    "keywords": [],
    "prerequisites": [],
    "children": [
        {
            "id": "num_algebra",
            "name": "数与代数",
            "parent_id": "root",
            "level": 1,
            "keywords": ["数", "代数", "运算", "方程", "函数"],
            "prerequisites": [],
            "children": [
                {
                    "id": "rational_num",
                    "name": "有理数",
                    "parent_id": "num_algebra",
                    "level": 2,
                    "keywords": ["有理数", "正数", "负数", "整数", "分数"],
                    "prerequisites": [],
                    "children": [
                        {"id": "rational_concept", "name": "有理数的概念", "parent_id": "rational_num", "level": 3,
                         "keywords": ["有理数", "分类", "定义"], "prerequisites": []},
                        {"id": "rational_op", "name": "有理数的运算", "parent_id": "rational_num", "level": 3,
                         "keywords": ["加法", "减法", "乘法", "除法", "乘方", "运算律", "运算", "计算"], "prerequisites": ["rational_concept"]},
                        {"id": "num_axis_abs", "name": "数轴与绝对值", "parent_id": "rational_num", "level": 3,
                         "keywords": ["数轴", "绝对值", "相反数"], "prerequisites": ["rational_concept"]},
                    ]
                },
                {
                    "id": "algebraic_expr",
                    "name": "整式",
                    "parent_id": "num_algebra",
                    "level": 2,
                    "keywords": ["整式", "单项式", "多项式", "代数式"],
                    "prerequisites": ["rational_num"],
                    "children": [
                        {"id": "expr_add_sub", "name": "整式的加减", "parent_id": "algebraic_expr", "level": 3,
                         "keywords": ["合并同类项", "去括号", "整式加减"], "prerequisites": ["rational_op"]},
                        {"id": "expr_mul_div", "name": "整式的乘除", "parent_id": "algebraic_expr", "level": 3,
                         "keywords": ["幂运算", "乘法公式", "整式乘除"], "prerequisites": ["expr_add_sub"]},
                        {"id": "factorization", "name": "因式分解", "parent_id": "algebraic_expr", "level": 3,
                         "keywords": ["因式分解", "提公因式", "公式法", "十字相乘"], "prerequisites": ["expr_mul_div"]},
                    ]
                },
                {
                    "id": "equation_ineq",
                    "name": "方程与不等式",
                    "parent_id": "num_algebra",
                    "level": 2,
                    "keywords": ["方程", "不等式", "解", "未知数"],
                    "prerequisites": ["algebraic_expr"],
                    "children": [
                        {"id": "linear_eq_1var", "name": "一元一次方程", "parent_id": "equation_ineq", "level": 3,
                         "keywords": ["一元一次方程", "移项", "合并同类项", "解方程"], "prerequisites": ["expr_add_sub"]},
                        {"id": "linear_eq_2var", "name": "二元一次方程组", "parent_id": "equation_ineq", "level": 3,
                         "keywords": ["二元一次方程组", "代入消元", "加减消元"], "prerequisites": ["linear_eq_1var"]},
                        {"id": "linear_ineq", "name": "一元一次不等式", "parent_id": "equation_ineq", "level": 3,
                         "keywords": ["不等式", "不等号", "解集", "不等式组"], "prerequisites": ["linear_eq_1var"]},
                        {"id": "quadratic_eq", "name": "一元二次方程", "parent_id": "equation_ineq", "level": 3,
                         "keywords": ["一元二次方程", "求根公式", "判别式", "韦达定理"], "prerequisites": ["factorization", "linear_eq_1var"]},
                    ]
                },
                {
                    "id": "function",
                    "name": "函数",
                    "parent_id": "num_algebra",
                    "level": 2,
                    "keywords": ["函数", "自变量", "因变量", "图像", "定义域"],
                    "prerequisites": ["equation_ineq"],
                    "children": [
                        {"id": "linear_func", "name": "一次函数", "parent_id": "function", "level": 3,
                         "keywords": ["一次函数", "正比例函数", "k值", "截距", "斜率"], "prerequisites": ["linear_eq_1var"]},
                        {"id": "inverse_func", "name": "反比例函数", "parent_id": "function", "level": 3,
                         "keywords": ["反比例函数", "双曲线", "k值"], "prerequisites": ["rational_op"]},
                        {"id": "quadratic_func", "name": "二次函数", "parent_id": "function", "level": 3,
                         "keywords": ["二次函数", "抛物线", "顶点", "对称轴", "开口方向"], "prerequisites": ["quadratic_eq", "linear_func"]},
                    ]
                },
            ]
        },
        {
            "id": "geometry",
            "name": "图形与几何",
            "parent_id": "root",
            "level": 1,
            "keywords": ["图形", "几何", "角", "线", "面", "证明"],
            "prerequisites": [],
            "children": [
                {
                    "id": "triangle",
                    "name": "三角形",
                    "parent_id": "geometry",
                    "level": 2,
                    "keywords": ["三角形", "内角和", "边", "角"],
                    "prerequisites": ["rational_num"],
                    "children": [
                        {"id": "congruent_tri", "name": "全等三角形", "parent_id": "triangle", "level": 3,
                         "keywords": ["全等", "SSS", "SAS", "ASA", "AAS", "HL"], "prerequisites": ["rational_op"]},
                        {"id": "similar_tri", "name": "相似三角形", "parent_id": "triangle", "level": 3,
                         "keywords": ["相似", "相似比", "AA", "SAS", "SSS"], "prerequisites": ["congruent_tri", "rational_op"]},
                        {"id": "right_tri", "name": "直角三角形", "parent_id": "triangle", "level": 3,
                         "keywords": ["直角三角形", "勾股定理", "30度", "斜边"], "prerequisites": ["congruent_tri"]},
                    ]
                },
                {
                    "id": "quadrilateral",
                    "name": "四边形",
                    "parent_id": "geometry",
                    "level": 2,
                    "keywords": ["四边形", "平行四边形", "矩形", "菱形", "正方形", "梯形"],
                    "prerequisites": ["triangle"],
                    "children": [
                        {"id": "parallelogram", "name": "平行四边形", "parent_id": "quadrilateral", "level": 3,
                         "keywords": ["平行四边形", "对边平行", "对角线"], "prerequisites": ["congruent_tri"]},
                        {"id": "special_quad", "name": "特殊平行四边形", "parent_id": "quadrilateral", "level": 3,
                         "keywords": ["矩形", "菱形", "正方形"], "prerequisites": ["parallelogram"]},
                    ]
                },
                {
                    "id": "circle",
                    "name": "圆",
                    "parent_id": "geometry",
                    "level": 2,
                    "keywords": ["圆", "半径", "直径", "弧", "弦", "圆心角", "圆周角"],
                    "prerequisites": ["triangle"],
                    "children": [
                        {"id": "circle_props", "name": "圆的性质", "parent_id": "circle", "level": 3,
                         "keywords": ["圆心角", "圆周角", "弧", "弦", "垂径定理"], "prerequisites": ["similar_tri"]},
                        {"id": "circle_pos", "name": "点与圆的位置关系", "parent_id": "circle", "level": 3,
                         "keywords": ["点在圆上", "点在圆内", "点在圆外", "切线"], "prerequisites": ["circle_props"]},
                    ]
                },
            ]
        },
        {
            "id": "stats_prob",
            "name": "统计与概率",
            "parent_id": "root",
            "level": 1,
            "keywords": ["统计", "概率", "数据", "频率", "随机"],
            "prerequisites": ["rational_num"],
            "children": [
                {"id": "data_collect", "name": "数据的收集与整理", "parent_id": "stats_prob", "level": 2,
                 "keywords": ["频数", "频率", "直方图", "扇形图", "条形图"], "prerequisites": ["rational_op"]},
                {"id": "simple_prob", "name": "简单概率", "parent_id": "stats_prob", "level": 2,
                 "keywords": ["概率", "随机事件", "等可能", "树状图", "列表法"], "prerequisites": ["data_collect"]},
            ]
        },
        {
            "id": "comprehensive",
            "name": "综合与实践",
            "parent_id": "root",
            "level": 1,
            "keywords": ["综合", "应用", "实践", "建模"],
            "prerequisites": ["num_algebra", "geometry"],
            "children": []
        },
    ]
}


class KnowledgeGraph:
    """知识图谱服务"""

    def __init__(self, graph_data: dict | None = None):
        self._raw = graph_data or MATH_KNOWLEDGE_GRAPH
        self._nodes: dict[str, dict] = {}  # id -> node
        self._children: dict[str, list[str]] = {}  # id -> [child_ids]
        self._dependents: dict[str, list[str]] = {}  # id -> [依赖它的节点IDs]（正向边）
        self._ancestors_cache: dict[str, list[str]] = {}
        self._precomputed: bool = False
        self._descendants_cache: dict[str, list[str]] = {}
        self._depth_cache: dict[str, int] = {}
        self._adjacency_cache: dict[str, list[str]] = {}
        self._flatten(self._raw)

    def _flatten(self, node: dict):
        """将树形结构展平为节点字典"""
        node_id = node["id"]
        self._nodes[node_id] = {
            "id": node_id,
            "name": node["name"],
            "parent_id": node.get("parent_id"),
            "level": node.get("level", 0),
            "keywords": node.get("keywords", []),
            "prerequisites": node.get("prerequisites", []),
        }

        children = node.get("children", [])
        self._children[node_id] = [c["id"] for c in children]

        # 构建正向依赖边：如果B的prerequisites包含A，则A→B
        for prereq_id in node.get("prerequisites", []):
            if prereq_id not in self._dependents:
                self._dependents[prereq_id] = []
            self._dependents[prereq_id].append(node_id)

        for child in children:
            self._flatten(child)

    def get_node(self, node_id: str) -> dict | None:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> dict[str, dict]:
        return self._nodes.copy()

    def get_children(self, node_id: str) -> list[str]:
        return self._children.get(node_id, [])

    def get_ancestors(self, node_id: str, _visited: set | None = None) -> list[str]:
        """获取所有祖先节点ID（从直接父节点到根节点）

        Args:
            node_id: 起始节点ID
            _visited: 内部使用，环检测已访问节点集合
        """
        if node_id in self._ancestors_cache:
            return self._ancestors_cache[node_id]

        # 环检测：防止prerequisites循环依赖导致无限递归
        if _visited is None:
            _visited = set()
        if node_id in _visited:
            logger.warning(f"[KnowledgeGraph] 检测到循环依赖: {node_id} 在祖先链中重复出现")
            return []
        _visited.add(node_id)

        ancestors = []
        current = self._nodes.get(node_id)
        while current and current.get("parent_id"):
            parent_id = current["parent_id"]
            if parent_id in ancestors:
                # 树形parent链中检测到环
                logger.warning(f"[KnowledgeGraph] 检测到parent循环: {parent_id}")
                break
            ancestors.append(parent_id)
            current = self._nodes.get(parent_id)

        # 加上前置依赖的知识点（跨分支依赖）
        node = self._nodes.get(node_id, {})
        for prereq_id in node.get("prerequisites", []):
            if prereq_id not in ancestors:
                ancestors.append(prereq_id)
                # 递归加入prereq的祖先（传递visited集合）
                prereq_ancestors = self.get_ancestors(prereq_id, _visited)
                for pa in prereq_ancestors:
                    if pa not in ancestors:
                        ancestors.append(pa)

        self._ancestors_cache[node_id] = ancestors
        return ancestors

    def get_depth(self, from_id: str, to_id: str) -> int | float:
        """计算从from_id到to_id的最短路径长度（沿正向依赖边）"""
        if from_id == to_id:
            return 0

        if self._precomputed:
            # 使用邻接表缓存的BFS
            from collections import deque
            visited = {from_id}
            queue = deque([(from_id, 0)])
            while queue:
                current, dist = queue.popleft()
                neighbors = self._adjacency_cache.get(current, [])
                for neighbor in neighbors:
                    if neighbor == to_id:
                        return dist + 1
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, dist + 1))
            return float("inf")

        # 原始BFS逻辑（作为fallback）
        from collections import deque
        visited = {from_id}
        queue = deque([(from_id, 0)])

        while queue:
            current, dist = queue.popleft()
            # 沿正向边扩展：children + dependents
            neighbors = list(self._children.get(current, []))
            neighbors.extend(self._dependents.get(current, []))

            for neighbor in neighbors:
                if neighbor == to_id:
                    return dist + 1
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))

        return float("inf")  # 不可达

    def search_by_keywords(self, text: str) -> list[str]:
        """关键词规则匹配：从文本中匹配知识点（含向上冒泡）"""
        matched = set()
        text_lower = text.lower()

        for node_id, node in self._nodes.items():
            for kw in node.get("keywords", []):
                if kw.lower() in text_lower:
                    matched.add(node_id)
                    # 向上冒泡：子节点匹配时，父节点也算匹配
                    parent_id = node.get("parent_id")
                    while parent_id and parent_id in self._nodes:
                        matched.add(parent_id)
                        parent_id = self._nodes[parent_id].get("parent_id")
                    break

        # 优先返回最具体的（level最高的）知识点
        sorted_matched = sorted(matched, key=lambda nid: self._nodes.get(nid, {}).get("level", 0), reverse=True)
        return sorted_matched

    def get_radar_dimensions(self) -> list[dict]:
        """获取雷达图的一级维度"""
        return [
            {"id": child_id, "name": self._nodes[child_id]["name"]}
            for child_id in self._children.get("root", [])
        ]

    def to_mermaid(self) -> str:
        """导出为Mermaid图"""
        lines = ["graph TD"]
        for node_id, node in self._nodes.items():
            if node["parent_id"] and node["parent_id"] in self._nodes:
                parent_name = self._nodes[node["parent_id"]]["name"]
                lines.append(f'    {node["parent_id"]}["{parent_name}"] --> {node_id}["{node["name"]}"]')
        return "\n".join(lines)

    def precompute(self):
        """预计算并缓存常用数据，启动时调用一次"""
        # 1. 预计算每个节点的ancestors
        self._ancestors_cache.clear()
        for node_id in self._nodes:
            self._ancestors_cache[node_id] = self.get_ancestors(node_id)

        # 2. 预计算每个节点的descendants
        self._descendants_cache.clear()
        for node_id in self._nodes:
            self._descendants_cache[node_id] = self._get_descendants(node_id)

        # 3. 预计算每个节点的depth（到根的最短距离）
        self._depth_cache.clear()
        for node_id in self._nodes:
            self._depth_cache[node_id] = self._compute_depth(node_id)

        # 4. 预计算邻接表（每个节点的所有邻居）
        self._adjacency_cache.clear()
        for node_id in self._nodes:
            neighbors = list(self._children.get(node_id, []))
            neighbors.extend(self._dependents.get(node_id, []))
            # 也加入prerequisites
            node = self._nodes.get(node_id, {})
            neighbors.extend(node.get("prerequisites", []))
            self._adjacency_cache[node_id] = list(set(neighbors))

        self._precomputed = True
        logger.info(f"[KnowledgeGraph] 预计算完成: {len(self._nodes)} 节点, "
              f"{len(self._ancestors_cache)} ancestors, "
              f"{len(self._descendants_cache)} descendants")

    def _get_descendants(self, node_id: str) -> list[str]:
        """获取所有后代节点ID"""
        descendants = []
        for child_id in self._children.get(node_id, []):
            descendants.append(child_id)
            descendants.extend(self._get_descendants(child_id))
        return descendants

    def _compute_depth(self, node_id: str, _visited: set | None = None) -> int:
        """计算节点到根的深度（含环检测）"""
        if _visited is None:
            _visited = set()
        if node_id in _visited:
            logger.warning(f"[KnowledgeGraph] _compute_depth检测到循环: {node_id}")
            return 0
        _visited.add(node_id)

        node = self._nodes.get(node_id, {})
        parent_id = node.get("parent_id")
        if not parent_id:
            return 0
        return 1 + self._compute_depth(parent_id, _visited)

    def get_precomputed_data(self) -> dict:
        """返回预计算数据的序列化版本"""
        return {
            "ancestors": {k: v for k, v in self._ancestors_cache.items()},
            "descendants": {k: v for k, v in self._descendants_cache.items()},
            "depth": {k: v for k, v in self._depth_cache.items()},
            "adjacency": {k: v for k, v in self._adjacency_cache.items()},
            "nodes_count": len(self._nodes),
            "precomputed": self._precomputed,
        }
