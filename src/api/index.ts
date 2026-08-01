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
 * 请求拦截器
 */
instance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 添加 Token（优先从 userStore，fallback 到 localStorage）
    const token = getToken()
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
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
      handleUnauthorized()
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
          } else {
            handleUnauthorized()
          }
          break
        case 403:
          antMessage.error('没有权限访问')
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

/**
 * 处理 401 未授权：清除登录状态并跳转登录页
 */
function handleUnauthorized() {
  antMessage.error('登录已过期，请重新登录')

  // 清除持久化存储
  localStorage.removeItem('oat_user_store')

  // 延迟跳转，确保消息提示先展示
  setTimeout(() => {
    const currentPath = window.location.pathname
    if (currentPath !== '/login' && currentPath !== '/register') {
      window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`
    }
  }, 500)
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
        const blob = new Blob([response.data])
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = filename
        link.click()
        URL.revokeObjectURL(link.href)
      })
      .catch((error) => {
        console.error('下载失败:', error)
      })
  }
}

export default instance
