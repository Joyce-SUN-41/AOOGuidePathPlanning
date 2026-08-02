import { request } from '@/api'
import type { LoginParams, LoginResult, RegisterParams, UserInfo } from '@/types'

/**
 * 后端 /auth/login 和 /auth/register 响应格式 (ResponseBase.data 展开后)
 * 对应后端 AuthResponse { token, userInfo }
 */
interface AuthResponseRaw {
  token: string
  /** 刷新令牌，用于 access token 过期时静默续期 */
  refreshToken?: string
  userInfo: {
    id: string
    username: string
    nickname: string
    avatar: string | null
    email: string | null
    phone: string | null
    role: string
    status: number
    createTime: string
  }
}

/**
 * 认证相关 API
 */
export const authApi = {
  /** 账号密码登录 — 调用 /auth/login 获取 token，再调用 /auth/me 获取用户信息 */
  async login(data: LoginParams): Promise<LoginResult> {
    // /auth/login 返回 ResponseBase[AuthResponse]，拦截器展开后得到 { token, userInfo }
    const authResp = await request.post<AuthResponseRaw>(
      '/auth/login',
      data as unknown as Record<string, unknown>
    )
    const accessToken = authResp.token

    // 用新 token 获取用户信息（直接 fetch 避免拦截器已存的旧 token 干扰）
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    const userResp = await fetch(`${baseUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    if (!userResp.ok) {
      throw new Error(`获取用户信息失败: ${userResp.status}`)
    }
    const userJson = await userResp.json()
    const userInfo: UserInfo = (userJson.data ?? userJson) as UserInfo

    return { token: accessToken, userInfo, refreshToken: authResp.refreshToken }
  },

  /** 用户注册 */
  async register(data: RegisterParams): Promise<LoginResult> {
    const authResp = await request.post<AuthResponseRaw>(
      '/auth/register',
      data as unknown as Record<string, unknown>
    )
    const accessToken = authResp.token

    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    const userResp = await fetch(`${baseUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    if (!userResp.ok) {
      throw new Error(`获取用户信息失败: ${userResp.status}`)
    }
    const userJson = await userResp.json()
    const userInfo: UserInfo = (userJson.data ?? userJson) as UserInfo

    return { token: accessToken, userInfo, refreshToken: authResp.refreshToken }
  },

  /** 退出登录 */
  logout(): Promise<void> {
    return request.post<void>('/auth/logout')
  },

  /** 刷新 token（需要存储并传递 refreshToken） */
  refreshToken(refreshToken: string): Promise<{ token: string }> {
    return request.post<{ token: string }>('/auth/refresh', {
      refresh_token: refreshToken
    } as unknown as Record<string, unknown>)
  }
}
