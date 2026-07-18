import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'

const data = [
  { name: '1月', total: 2450 },
  { name: '2月', total: 1820 },
  { name: '3月', total: 3100 },
  { name: '4月', total: 2750 },
  { name: '5月', total: 3200 },
  { name: '6月', total: 2890 },
  { name: '7月', total: 1560 },
  { name: '8月', total: 980 },
  { name: '9月', total: 3400 },
  { name: '10月', total: 3050 },
  { name: '11月', total: 3580 },
  { name: '12月', total: 2720 },
]

export function Overview() {
  return (
    <ResponsiveContainer width='100%' height={350}>
      <BarChart data={data}>
        <XAxis
          dataKey='name'
          stroke='#888888'
          fontSize={12}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          direction='ltr'
          stroke='#888888'
          fontSize={12}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value) => `${value}份`}
        />
        <Bar
          dataKey='total'
          fill='currentColor'
          radius={[4, 4, 0, 0]}
          className='fill-primary'
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
