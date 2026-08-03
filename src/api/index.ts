import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { ApiResponse } from '@/types'
import { message as antMessage } from 'ant-design-vue'

/**
 * 创建 Axios 实例
 */
const instance: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json;charset=utf-8'
  }
})

/**
 * AI / 重计算类接口的较长超时（秒）。其余接口沿用全局默认 15s。
 * 这类接口（大模型生成、RAG 检索、AOO 路径优化、认知诊断）常见耗时 > 15s，
 * 用全局短超时会误判超时。
 */
const LONG_TIMEOUT_ENDPOINTS = [
  '/chat',
  '/agent',
  '/rag',
  '/aoo',
  '/optimize',
  '/diagnosis',
]
const LONG_TIMEOUT_MS = 120_000

/**
 * 请求拦截器
 */
instance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 添加 Token（优先从 userStore，fallback 到 localStorage）
    const token = getToken()
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }

    // 按接口类型分级设置超时：AI / 重计算类接口给更长超时
    const url = config.url || ''
    if (config.timeout === undefined && LONG_TIMEOUT_ENDPOINTS.some((e) => url.includes(e))) {
      config.timeout = LONG_TIMEOUT_MS
    }

    // 开发环境打印请求信息
    if (import.meta.env.DEV) {
      console.log(`[Request] ${config.method?.toUpperCase()} ${config.url}`, config.params || config.data)
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * 响应拦截器
 */
instance.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const { code, message: msg, data } = response.data

    // 业务成功
    if (code === 0 || code === 200) {
      return data as unknown as AxiosResponse
    }

    // 业务自定义未授权码
    if (code === 401) {
      // 业务层 401：触发登出流程，并 reject 让调用方感知
      void handleUnauthorized(errorWithResponse(response))
      return Promise.reject(new Error(msg || '登录已过期'))
    }

    // 业务错误
    antMessage.error(msg || '请求失败')
    return Promise.reject(new Error(msg || '请求失败'))
  },
  (error) => {
    if (error.response) {
      const { status, config, data } = error.response

      switch (status) {
        case 401:
          // 登录接口的 401 说明用户名或密码错误，不要当作会话过期
          if (config?.url?.includes('/auth/login')) {
            const detail = data?.detail || '用户名或密码错误'
            antMessage.error(detail)
            return Promise.reject(error)
          }
          // access token 过期：尝试静默刷新后重放原请求
          return handleUnauthorized(error)
        case 403:
          antMessage.error('没有权限访问')
          break
        case 409:
          // 资源冲突：注册时用户名/邮箱已存在，透传后端具体原因
          antMessage.error(data?.detail || '该用户名或邮箱已被注册')
          break
        case 404:
          antMessage.error('请求的资源不存在')
          break
        case 500:
          antMessage.error('服务器错误')
          break
        default:
          antMessage.error(`请求失败 (${status})`)
      }
    } else if (error.message?.includes('timeout')) {
      antMessage.error('请求超时，请稍后重试')
    } else {
      antMessage.error('网络异常，请检查网络连接')
    }

    return Promise.reject(error)
  }
)

/**
 * 获取 token
 * 直接从 pinia-plugin-persistedstate 持久化存储读取，避免循环依赖
 */
export function getToken(): string | null {
  try {
    const raw = localStorage.getItem('oat_user_store')
    if (raw) {
      const parsed = JSON.parse(raw)
      return parsed?.token || null
    }
  } catch {
    // ignore
  }
  return null
}

/** 从持久化存储读取 refresh token（与 getToken 保持一致的来源） */
function getRefreshToken(): string | null {
  try {
    const raw = localStorage.getItem('oat_user_store')
    if (raw) {
      const parsed = JSON.parse(raw)
      return parsed?.refreshToken || null
    }
  } catch {
    // ignore
  }
  return null
}

/** 刷新中的并发锁：多个 401 请求共享同一次刷新 */
let refreshingPromise: Promise<string | null> | null = null

/**
 * 使用 refresh token 换取新的 access token。
 * 通过 refreshingPromise 保证并发 401 只真正刷新一次，其余请求排队复用结果。
 * 刷新成功后同步更新 userStore（动态 import 避免与 store 形成循环依赖）。
 */
async function doRefreshToken(): Promise<string | null> {
  if (refreshingPromise) {
    return refreshingPromise
  }

  refreshingPromise = (async () => {
    const rt = getRefreshToken()
    if (!rt) return null
    try {
      const { authApi } = await import('@/api/modules/auth')
      const res = await authApi.refreshToken(rt)
      const newToken = res?.token
      if (!newToken) return null
      // 同步到 userStore（更新内存 + 持久化）
      const { useUserStore } = await import('@/stores/user')
      const userStore = useUserStore()
      // 后端 refresh 同时返回新的 refreshToken
      const newRt = (res as unknown as { refreshToken?: string }).refreshToken
      userStore.setTokens(newToken, newRt)
      return newToken
    } catch {
      return null
    } finally {
      // 释放锁，允许下一次刷新
      refreshingPromise = null
    }
  })()

  return refreshingPromise
}

/**
 * 处理 401 未授权：尝试用 refresh token 静默续期并重放原请求；
 * 刷新失败（无 refresh / 已过期）才真正登出跳转登录页。
 */
async function handleUnauthorized(error: unknown): Promise<unknown> {
  const originalRequest = (error as { config?: InternalAxiosRequestConfig & { _retry?: boolean } })?.config

  // 避免同一请求无限重试
  if (originalRequest && originalRequest._retry) {
    return forceLogout()
  }

  const newToken = await doRefreshToken()
  if (!newToken || !originalRequest) {
    return forceLogout()
  }

  // 重放原请求
  originalRequest._retry = true
  originalRequest.headers = originalRequest.headers || {}
  originalRequest.headers.Authorization = `Bearer ${newToken}`
  return instance(originalRequest)
}

/** 真正的登出：清除状态并跳转登录页（使用 router.push 保留 SPA 体验） */
function forceLogout(): Promise<never> {
  // 清除持久化存储
  localStorage.removeItem('oat_user_store')

  // 动态导入 router 避免循环依赖
  return import('@/router').then(({ default: router }) => {
    const currentPath = router.currentRoute.value.fullPath
    if (currentPath !== '/login' && currentPath !== '/register') {
      router.push(`/login?redirect=${encodeURIComponent(currentPath)}`)
    }
    return Promise.reject(new Error('登录已过期，请重新登录'))
  })
}

/** 构造一个带 response 的 error 对象，供业务 401 码复用统一处理 */
function errorWithResponse(response: AxiosResponse): unknown {
  return Object.assign(new Error('unauthorized'), { response })
}

/**
 * 通用请求方法
 */
export const request = {
  get<T = unknown>(url: string, params?: Record<string, unknown>, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, { params, ...config }) as unknown as Promise<T>
  },

  post<T = unknown>(url: string, data?: Record<string, unknown>, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config) as unknown as Promise<T>
  },

  put<T = unknown>(url: string, data?: Record<string, unknown>, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config) as unknown as Promise<T>
  },

  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config) as unknown as Promise<T>
  },

  upload<T = unknown>(url: string, formData: FormData, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      ...config
    }) as unknown as Promise<T>
  },

  download(url: string, filename: string): void {
    instance
      .get(url, { responseType: 'blob' })
      .then((response) => {
        // 响应拦截器已返回 data，blob 场景下 response 即为 Blob 本体
        const blob = (response as unknown as Blob)
        if (!(blob instanceof Blob) || blob.size === 0) {
          antMessage.error('下载内容为空或格式异常')
          return
        }
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = filename
        link.click()
        URL.revokeObjectURL(link.href)
      })
      .catch((error) => {
        console.error('下载失败:', error)
        antMessage.error('下载失败，请稍后重试')
      })
  }
}

export default instance
