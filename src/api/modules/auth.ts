import { request } from '@/api'
import type { LoginParams, LoginResult, RegisterParams } from '@/types'

/**
 * 认证相关 API
 */
export const authApi = {
  /** 账号密码登录 */
  login(data: LoginParams): Promise<LoginResult> {
    return request.post<LoginResult>('/auth/login', data as unknown as Record<string, unknown>)
  },

  /** 用户注册 */
  register(data: RegisterParams): Promise<LoginResult> {
    return request.post<LoginResult>('/auth/register', data as unknown as Record<string, unknown>)
  },

  /** 退出登录 */
  logout(): Promise<void> {
    return request.post<void>('/auth/logout')
  },

  /** 刷新 token */
  refreshToken(): Promise<{ token: string }> {
    return request.post<{ token: string }>('/auth/refresh')
  }
}
