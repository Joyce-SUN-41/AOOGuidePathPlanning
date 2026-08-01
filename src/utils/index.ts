/**
 * 工具函数集合
 */

/**
 * 格式化日期
 */
export const formatDate = (date: Date | string | number, fmt = 'yyyy-MM-dd HH:mm:ss'): string => {
  const d = new Date(date)
  const o: Record<string, number> = {
    'M+': d.getMonth() + 1,
    'd+': d.getDate(),
    'H+': d.getHours(),
    'm+': d.getMinutes(),
    's+': d.getSeconds(),
    'q+': Math.floor((d.getMonth() + 3) / 3),
    S: d.getMilliseconds()
  }
  let result = fmt
  if (/(y+)/.test(result)) {
    result = result.replace(RegExp.$1, String(d.getFullYear()).slice(4 - RegExp.$1.length))
  }
  for (const k in o) {
    if (new RegExp(`(${k})`).test(result)) {
      const val = o[k]!
      result = result.replace(
        RegExp.$1,
        RegExp.$1.length === 1 ? String(val) : String(val).padStart(2, '0')
      )
    }
  }
  return result
}

/**
 * 深拷贝
 */
export const deepClone = <T>(obj: T): T => {
  if (obj === null || typeof obj !== 'object') return obj
  return JSON.parse(JSON.stringify(obj))
}

/**
 * 防抖
 */
export const debounce = <T extends (...args: unknown[]) => unknown>(fn: T, delay: number) => {
  let timer: ReturnType<typeof setTimeout> | null = null
  return function (this: unknown, ...args: Parameters<T>) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn.apply(this, args), delay)
  }
}

/**
 * 节流
 */
export const throttle = <T extends (...args: unknown[]) => unknown>(fn: T, delay: number) => {
  let lastTime = 0
  return function (this: unknown, ...args: Parameters<T>) {
    const now = Date.now()
    if (now - lastTime >= delay) {
      lastTime = now
      fn.apply(this, args)
    }
  }
}

/**
 * 树形数据转换
 */
export const listToTree = <T extends { id: number | string; parentId: number | string }>(
  list: T[],
  parentId: number | string = 0
): (T & { children?: T[] })[] => {
  return list
    .filter((item) => item.parentId === parentId)
    .map((item) => ({
      ...item,
      children: listToTree(list, item.id)
    }))
}

/**
 * 获取嵌套对象属性值
 */
export const getNestedValue = (obj: Record<string, unknown>, path: string): unknown => {
  return path.split('.').reduce((acc: unknown, key: string) => {
    if (acc && typeof acc === 'object') {
      return (acc as Record<string, unknown>)[key]
    }
    return undefined
  }, obj)
}

/**
 * 判断是否为空值
 */
export const isEmpty = (value: unknown): boolean => {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value) && value.length === 0) return true
  if (typeof value === 'object' && Object.keys(value as object).length === 0) return true
  return false
}
