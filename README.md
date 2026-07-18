# 智阅π ZhiReviewPi

> 飞书原生人机协作批改闭环系统 — AI预批改，老师终审裁，学生闭环订正

## 项目简介

智阅π是面向K12教育场景的人机协作批改闭环系统，覆盖数学计算题、几何证明题、语文作文三大场景。核心定位为"批改不是终点，订正才是"——实现 **布置→提交→预批改→老师审核→推送订正→二次批改→学情更新** 全链路闭环，深度融合飞书AI生态。

### 核心特性

- 🤖 **双引擎OCR融合** — 百度手写OCR API + PaddleOCR本地推理，置信度加权融合，低置信度自动标黄交给教师审核
- 📝 **柔性Rubric评分** — LLM自动推导步骤评分标准，教师一键确认/修改，模板跨班复用
- ✍️ **语文作文四维评分** — 内容40%/结构20%/语言25%/书写15%，5种错因标签对齐写作DAG，三级降级容灾
- 📐 **几何题VL视觉理解** — Qwen3-VL-32B-Instruct识别图形类型与标注信息，辅助线评估
- 🧠 **34节点知识图谱 + DecayPropagate归因** — 方向性衰减传播，输出可解释薄弱根源路径+雷达图
- 🔄 **订正闭环** — 批改→推送订正→二次批改→学情更新，"错题必闭环"
- 📚 **错题本增强** — 分层推荐（优等生/中等生/学困生），练习模式自动评分
- 💬 **飞书原生协同** — Aily智能伙伴 + 多维表格审核 + IM消息推送

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                   L4 飞书协同层                    │
│    Aily对话 · 多维表格审核 · IM订正推送            │
├─────────────────────────────────────────────────┤
│                   L3 知识归因层                    │
│   34节点知识图谱 · DecayPropagate · 写作能力DAG    │
├─────────────────────────────────────────────────┤
│                   L2 批改层                       │
│  MathGrader(过程分) · EssayGrader(四维) · 柔性Rubric │
│            多模型路由 · 三级降级容灾                │
├─────────────────────────────────────────────────┤
│                   L1 识别层                       │
│   百度OCR + PaddleOCR融合 · Qwen3-VL几何理解      │
└─────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | React + TypeScript + Vite + Ant Design + ECharts |
| 后端 | Python FastAPI + Uvicorn |
| OCR | 百度手写OCR API + PaddleOCR (本地推理) |
| LLM | 硅基流动 Qwen2.5-14B/7B + Qwen3-VL-32B-Instruct + 火山引擎豆包 |
| 知识图谱 | 34节点4层课标骨架树 + DecayPropagate归因 |
| 飞书协同 | Aily + 多维表格 + IM |

## 项目结构

```
智阅π/
├── app/                          # 后端模块
│   ├── main.py                   # FastAPI 主入口（40+ API端点）
│   ├── grader.py                 # 批改引擎（MathGrader + EssayGrader + RubricGenerator）
│   ├── attribution.py            # DecayPropagate 归因算法
│   ├── knowledge_graph.py        # 34节点知识图谱
│   ├── writing_graph.py          # 写作能力DAG图谱
│   ├── correction.py             # 订正闭环
│   ├── similar_question.py       # 错题本 + 分层推荐
│   ├── ocr.py                    # 双引擎OCR融合
│   ├── geometry_analyzer.py      # VL几何检测
│   ├── model_router.py           # 多模型动态路由
│   ├── alert_service.py          # 学情预警
│   ├── batch_service.py          # 批量批改
│   ├── group_service.py          # 小组协同
│   ├── question_bank.py          # 题库缓存
│   ├── subject_framework.py      # 4学科框架
│   ├── answer_solver.py          # 答案求解
│   ├── export_service.py         # 数据导出
│   ├── config.py                 # 配置管理
│   └── llm_utils.py              # LLM工具
│
├── tests/                        # 172项pytest
│   ├── test_essay_grader.py      # 作文批改
│   ├── test_grading_pipeline_dispatch.py  # 分发
│   ├── test_attribution.py       # 归因
│   ├── test_knowledge_graph.py   # 知识图谱
│   ├── test_writing_graph.py     # 写作图谱
│   ├── test_geometry_analyzer.py # 几何检测
│   ├── test_model_router.py      # 模型路由
│   ├── test_question_bank.py     # 题库
│   ├── test_subject_framework.py # 学科框架
│   ├── test_alert_service.py     # 预警
│   ├── test_batch_service.py     # 批量
│   ├── test_group_service.py     # 小组
│   └── conftest.py
│
├── frontend/                     # React前端
│   └── src/
│       ├── features/             # 功能模块
│       ├── components/           # 通用组件
│       ├── hooks/                # 自定义Hooks
│       ├── lib/                  # 工具库
│       ├── stores/               # 状态管理
│       └── routes/               # 路由
│
├── data/                         # 运行时数据
├── .env.example                  # 环境变量模板
└── requirements.txt              # Python依赖
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PaddleOCR + PaddlePaddle

### 后端启动

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 启动后端
uvicorn app.main:app --reload --port 8000
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

### 运行测试

```bash
python -m pytest tests/ -v
```

## 核心创新

| 创新 | 描述 |
|------|------|
| 人机协作三审制 | AI预批改为建议、教师终审为定论、订正后二次验证为闭环 |
| 柔性Rubric | AI推导评分标准+教师确认+模板跨班复用，过程分可控可复现 |
| DecayPropagate归因 | 面向知识DAG的方向性衰减传播，参数有教育学含义，输出可解释薄弱根源路径 |
| EssayGrader四维评分 | 内容/结构/语言/书写独立评分+5错因标签对齐写作DAG+三级降级 |
| 飞书原生闭环 | Aily+多维表格+IM全链路，结构性壁垒 |

## 路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 数学批改核心 + 知识图谱 + 飞书协同 | ✅ 完成 |
| Phase 2 | 几何VL增强 + 错题本 + 订正闭环 + 批量批改 | ✅ 完成 |
| Phase 2.5 | 语文作文四维评分 + 错因归因联动 | ✅ 完成 |
| Phase 3 | CapGeo几何增强 + 可解释性 + 多学科扩展 | 📋 规划中 |

## License

MIT
