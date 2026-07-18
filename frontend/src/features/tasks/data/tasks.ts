import { faker } from '@faker-js/faker'

// Set a fixed seed for consistent data generation
faker.seed(12345)

const taskTitles = [
  '第三章 一元一次方程 课后练习',
  '几何证明专题 批改',
  '期中作文批改 高二(3)班',
  '第四章 二次根式 随堂测验',
  '物理力学单元卷 批改',
  '英语阅读理解 课后作业',
  '第五章 全等三角形 证明题',
  '化学方程式配平练习',
  '数学周测 函数与导数',
  '语文默写检测 古诗文',
  '第六章 圆的性质 练习册',
  '历史材料分析题 批改',
  '生物实验报告 批改',
  '第七章 概率统计 课后练习',
  '政治论述题 期中批改',
  '英语完形填空 专题训练',
  '第八章 相似三角形 证明题',
  '物理电磁学 课后作业',
  '数学月考 立体几何',
  '地理读图分析 批改',
  '第九章 一元二次方程 练习',
  '语文议论文写作 批改',
  '化学有机推断 专题训练',
  '第十章 数据收集与整理 随堂',
  '英语书面表达 期末批改',
  '三角函数综合练习',
  '语文文言文翻译 检测',
  '物理光学 课后练习',
  '生物遗传题 专题批改',
  '数学不等式 课堂测验',
  '化学实验操作 报告批改',
  '历史简答题 单元批改',
  '英语语法填空 专题训练',
  '物理热学 课后作业',
  '语文散文阅读 批改',
  '数学数列求和 练习册',
  '政治辨析题 随堂批改',
  '地理综合题 期中批改',
  '生物生态学 课后练习',
  '英语短文改错 批改',
  '向量与坐标 综合练习',
  '语文诗歌鉴赏 批改',
  '化学电化学 专题训练',
  '物理动量守恒 课后作业',
  '数学解析几何 月考批改',
  '历史论述题 期末批改',
  '英语听力填空 课后练习',
  '政治开放性试题 批改',
  '地理区域分析 专题批改',
  '生物细胞生物学 随堂测验',
]

const taskDescriptions = [
  '请按照评分标准逐题批改，注意解题步骤的规范性，对错误之处给出详细批注。',
  '重点检查证明过程的逻辑严密性，每一步推理需有充分依据，不规范的写法需标注。',
  '作文批改请关注立意、结构、语言三个维度，给出具体修改建议和范文对照。',
  '计算题需逐步检查运算过程，常见错误类型请归纳标注，方便学生复盘。',
  '请检查公式应用是否正确，单位是否统一，有效数字保留是否规范。',
  '阅读理解需关注答案要点的完整性，信息提取是否准确，表达是否清晰。',
  '证明题需审查逻辑链条完整性，辅助线标注是否规范，结论是否充分。',
  '配平练习需逐一检查原子守恒和电荷守恒，标注常见配平误区。',
  '函数题重点检查定义域、值域分析，图像变换步骤，极值求解过程。',
  '默写检测逐句对照原文，错字、漏字、颠倒均需标注扣分。',
]

const assignees = [
  '张老师', '李老师', '王老师', '刘老师', '陈老师',
  '杨老师', '赵老师', '黄老师', '周老师', '吴老师',
]

export const tasks = Array.from({ length: 100 }, () => {
  const statuses = [
    'backlog',
    'in progress',
    'done',
    'review',
    'verified',
  ] as const
  const labels = ['calculation', 'geometry', 'composition'] as const
  const priorities = ['low', 'medium', 'high'] as const

  return {
    id: `TASK-${faker.number.int({ min: 1000, max: 9999 })}`,
    title: faker.helpers.arrayElement(taskTitles),
    status: faker.helpers.arrayElement(statuses),
    label: faker.helpers.arrayElement(labels),
    priority: faker.helpers.arrayElement(priorities),
    createdAt: faker.date.past(),
    updatedAt: faker.date.recent(),
    assignee: faker.helpers.arrayElement(assignees),
    description: faker.helpers.arrayElement(taskDescriptions),
    dueDate: faker.date.future(),
  }
})
