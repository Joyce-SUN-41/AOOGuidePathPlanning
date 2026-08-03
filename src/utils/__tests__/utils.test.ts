/**
 * utils.test.ts — 工具函数单元测试示例
 *
 * 运行: npx vitest run src/utils/__tests__/utils.test.ts
 */
import { describe, it, expect } from 'vitest'

// ── 待测函数定义（生产代码在 src/utils/index.ts） ──

/** 格式化数字为指定小数位 */
function formatNumber(value: number, decimals = 2): string {
  return value.toFixed(decimals)
}

/** 计算掌握度等级 */
function classifyMasteryLevel(value: number): string {
  if (value >= 0.85) return 'excellent'
  if (value >= 0.7) return 'proficient'
  if (value >= 0.5) return 'developing'
  return 'weak'
}

/** 难度标签映射 */
function difficultyLabel(level: number): string {
  const map: Record<number, string> = {
    1: '基础',
    2: '简单',
    3: '中等',
    4: '较难',
    5: '困难'
  }
  return map[level] ?? '未知'
}

/** 计算完成百分比 */
function calcPercent(done: number, total: number): number {
  if (total <= 0) return 0
  return Math.round((done / total) * 100)
}

// ── 测试用例 ──

describe('formatNumber', () => {
  it('默认保留两位小数', () => {
    expect(formatNumber(3.14159)).toBe('3.14')
  })

  it('整数补零', () => {
    expect(formatNumber(5)).toBe('5.00')
  })

  it('指定小数位', () => {
    expect(formatNumber(3.14159, 3)).toBe('3.142')
  })
})

describe('classifyMasteryLevel', () => {
  it('>= 0.85 → excellent', () => {
    expect(classifyMasteryLevel(0.85)).toBe('excellent')
    expect(classifyMasteryLevel(0.95)).toBe('excellent')
  })

  it('0.70 ~ 0.85 → proficient', () => {
    expect(classifyMasteryLevel(0.7)).toBe('proficient')
    expect(classifyMasteryLevel(0.84)).toBe('proficient')
  })

  it('0.50 ~ 0.70 → developing', () => {
    expect(classifyMasteryLevel(0.5)).toBe('developing')
    expect(classifyMasteryLevel(0.69)).toBe('developing')
  })

  it('< 0.50 → weak', () => {
    expect(classifyMasteryLevel(0.49)).toBe('weak')
    expect(classifyMasteryLevel(0)).toBe('weak')
  })
})

describe('difficultyLabel', () => {
  it('返回正确标签', () => {
    expect(difficultyLabel(1)).toBe('基础')
    expect(difficultyLabel(3)).toBe('中等')
    expect(difficultyLabel(5)).toBe('困难')
  })

  it('未知等级兜底', () => {
    expect(difficultyLabel(6)).toBe('未知')
    expect(difficultyLabel(0)).toBe('未知')
  })
})

describe('calcPercent', () => {
  it('标准计算', () => {
    expect(calcPercent(50, 200)).toBe(25)
    expect(calcPercent(3, 10)).toBe(30)
  })

  it('total <= 0 返回 0', () => {
    expect(calcPercent(10, 0)).toBe(0)
    expect(calcPercent(0, 0)).toBe(0)
  })

  it('完成数超过总数', () => {
    expect(calcPercent(200, 100)).toBe(200) // 业务层自行处理
  })
})
