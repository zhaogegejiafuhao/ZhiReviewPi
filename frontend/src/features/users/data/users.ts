const studentNames = [
  { firstName: '明', lastName: '李', username: 'liming', email: 'liming@student.edu.cn', phoneNumber: '+86 13800001001' },
  { firstName: '芳', lastName: '王', username: 'wangfang', email: 'wangfang@student.edu.cn', phoneNumber: '+86 13800001002' },
  { firstName: '伟', lastName: '张', username: 'zhangwei', email: 'zhangwei@student.edu.cn', phoneNumber: '+86 13800001003' },
  { firstName: '静', lastName: '赵', username: 'zhaojing', email: 'zhaojing@student.edu.cn', phoneNumber: '+86 13800001004' },
  { firstName: '浩', lastName: '陈', username: 'chenhao', email: 'chenhao@student.edu.cn', phoneNumber: '+86 13800001005' },
  { firstName: '洋', lastName: '刘', username: 'liuyang', email: 'liuyang@student.edu.cn', phoneNumber: '+86 13800001006' },
  { firstName: '敏', lastName: '周', username: 'zhoumin', email: 'zhoumin@student.edu.cn', phoneNumber: '+86 13800001007' },
  { firstName: '鹏', lastName: '孙', username: 'sunpeng', email: 'sunpeng@student.edu.cn', phoneNumber: '+86 13800001008' },
  { firstName: '婷', lastName: '吴', username: 'wuting', email: 'wuting@student.edu.cn', phoneNumber: '+86 13800001009' },
  { firstName: '强', lastName: '郑', username: 'zhengqiang', email: 'zhengqiang@student.edu.cn', phoneNumber: '+86 13800001010' },
  { firstName: '雪', lastName: '黄', username: 'huangxue', email: 'huangxue@student.edu.cn', phoneNumber: '+86 13800001011' },
  { firstName: '磊', lastName: '林', username: 'linlei', email: 'linlei@student.edu.cn', phoneNumber: '+86 13800001012' },
  { firstName: '颖', lastName: '何', username: 'heying', email: 'heying@student.edu.cn', phoneNumber: '+86 13800001013' },
  { firstName: '杰', lastName: '马', username: 'majie', email: 'majie@student.edu.cn', phoneNumber: '+86 13800001014' },
  { firstName: '丽', lastName: '罗', username: 'luoli', email: 'luoli@student.edu.cn', phoneNumber: '+86 13800001015' },
]

const statuses: ('活跃' | '休眠')[] = ['活跃', '休眠']

function randomDate(start: Date, end: Date): Date {
  return new Date(start.getTime() + Math.random() * (end.getTime() - start.getTime()))
}

export const users = Array.from({ length: 500 }, (_, i) => {
  const base = studentNames[i % studentNames.length]
  const suffix = i >= studentNames.length ? `${Math.floor(i / studentNames.length) + 1}` : ''
  return {
    id: crypto.randomUUID?.() ?? `${i + 1}`,
    firstName: base.firstName,
    lastName: base.lastName,
    username: base.username + suffix,
    email: base.username + suffix + '@student.edu.cn',
    phoneNumber: base.phoneNumber,
    status: i < 12 ? '活跃' : statuses[i % 2],
    role: '学生' as const,
    createdAt: randomDate(new Date(2024, 0, 1), new Date(2025, 5, 1)),
    updatedAt: randomDate(new Date(2025, 5, 1), new Date()),
  }
})
