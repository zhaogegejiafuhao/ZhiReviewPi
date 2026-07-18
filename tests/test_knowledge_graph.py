"""KnowledgeGraph 知识图谱核心逻辑单元测试

测试目标：
- 默认初始化与自定义初始化
- precompute 预计算与节点展平
- get_node / get_children / get_ancestors 查询
- _compute_depth 深度计算（根=0，一级=1，叶=3）
- search_by_keywords 关键词匹配（含向上冒泡）
- get_radar_dimensions 雷达维度（数与代数/图形与几何/统计与概率/综合与实践）
"""
from app.knowledge_graph import KnowledgeGraph, MATH_KNOWLEDGE_GRAPH


# ===== 初始化测试 =====


def test_init_default():
    """默认初始化使用 MATH_KNOWLEDGE_GRAPH，节点数 > 0"""
    kg = KnowledgeGraph()
    nodes = kg.get_all_nodes()
    assert len(nodes) > 0
    # root 节点必须存在
    assert "root" in nodes


def test_init_custom_graph():
    """使用自定义图谱数据初始化"""
    custom = {
        "id": "root",
        "name": "自定义",
        "parent_id": None,
        "level": 0,
        "keywords": [],
        "prerequisites": [],
        "children": [
            {"id": "child1", "name": "子节点1", "parent_id": "root", "level": 1,
             "keywords": ["测试"], "prerequisites": []},
        ],
    }
    kg = KnowledgeGraph(custom)
    nodes = kg.get_all_nodes()
    assert len(nodes) == 2
    assert "child1" in nodes


# ===== precompute 测试 =====


def test_precompute_nodes_count():
    """precompute 后节点数量合理（初中数学图谱 > 30）"""
    kg = KnowledgeGraph()
    kg.precompute()
    nodes = kg.get_all_nodes()
    assert len(nodes) > 30
    # 预计算标志为 True
    assert kg._precomputed is True


# ===== get_node 测试 =====


def test_get_node_exists():
    """获取已知节点 rational_num 返回正确数据"""
    kg = KnowledgeGraph()
    node = kg.get_node("rational_num")
    assert node is not None
    assert node["id"] == "rational_num"
    assert node["name"] == "有理数"
    assert node["level"] == 2
    assert "有理数" in node["keywords"]


def test_get_node_not_exists():
    """不存在的节点 ID 返回 None"""
    kg = KnowledgeGraph()
    assert kg.get_node("nonexistent_node") is None


def test_get_node_root():
    """获取根节点 root"""
    kg = KnowledgeGraph()
    node = kg.get_node("root")
    assert node is not None
    assert node["id"] == "root"
    assert node["name"] == "初中数学"
    assert node["level"] == 0
    assert node["parent_id"] is None


# ===== get_children 测试 =====


def test_get_children_of_root():
    """root 的 children 是 4 个一级模块"""
    kg = KnowledgeGraph()
    children = kg.get_children("root")
    assert len(children) == 4
    expected_ids = {"num_algebra", "geometry", "stats_prob", "comprehensive"}
    assert set(children) == expected_ids


def test_get_children_leaf():
    """叶节点（level=3）的 children 为空列表"""
    kg = KnowledgeGraph()
    # rational_concept 是 level=3 叶节点
    children = kg.get_children("rational_concept")
    assert children == []


# ===== get_ancestors 测试 =====


def test_get_ancestors_leaf():
    """叶节点的祖先路径包含直接父节点和 root"""
    kg = KnowledgeGraph()
    # rational_concept → rational_num → num_algebra → root
    ancestors = kg.get_ancestors("rational_concept")
    # 直接父节点 rational_num 必须在祖先中
    assert "rational_num" in ancestors
    # root 必须在祖先中
    assert "root" in ancestors
    # num_algebra 必须在祖先中
    assert "num_algebra" in ancestors


def test_get_ancestors_root():
    """root 的祖先为空列表"""
    kg = KnowledgeGraph()
    ancestors = kg.get_ancestors("root")
    assert ancestors == []


# ===== _compute_depth 测试 =====


def test_compute_depth_root():
    """root 到根的深度为 0"""
    kg = KnowledgeGraph()
    assert kg._compute_depth("root") == 0


def test_compute_depth_level1():
    """一级模块（num_algebra）深度为 1"""
    kg = KnowledgeGraph()
    assert kg._compute_depth("num_algebra") == 1


def test_compute_depth_level3():
    """叶节点（rational_concept，level=3）深度为 3"""
    kg = KnowledgeGraph()
    assert kg._compute_depth("rational_concept") == 3


# ===== search_by_keywords 测试 =====


def test_search_by_keywords_match():
    """'有理数'搜索到相关节点（至少包含 rational_num 或 rational_concept）"""
    kg = KnowledgeGraph()
    matched = kg.search_by_keywords("有理数的加减运算")
    assert len(matched) > 0
    # 至少有一个匹配节点是 level >= 2 的具体知识点
    matched_names = {kg.get_node(nid)["name"] for nid in matched if kg.get_node(nid)}
    # "有理数" 关键词应在 rational_num 或 rational_concept 中
    assert "有理数" in matched_names or "有理数的概念" in matched_names or "有理数的运算" in matched_names


def test_search_by_keywords_no_match():
    """无关关键词返回空列表"""
    kg = KnowledgeGraph()
    # 使用不包含任何图谱关键词的文本（"方程"会匹配equation_ineq，需避免）
    matched = kg.search_by_keywords("量子纠缠态薛定谔测量")
    assert matched == []


# ===== get_radar_dimensions 测试 =====


def test_get_radar_dimensions():
    """雷达维度有 4 个（数与代数/图形与几何/统计与概率/综合与实践）"""
    kg = KnowledgeGraph()
    dims = kg.get_radar_dimensions()
    assert len(dims) == 4
    dim_names = {d["name"] for d in dims}
    assert dim_names == {"数与代数", "图形与几何", "统计与概率", "综合与实践"}
