import { request } from '@/api'
import type { UserInfo } from '@/types'

/**
 * 用户 API 模块示例
 */
export const userApi = {
  /** 获取用户信息 */
  getUserInfo() {
    return request.get<UserInfo>('/auth/me')
  },

  /** 更新用户信息 */
  updateUserInfo(data: Partial<UserInfo>) {
    if (!data.id) {
      throw new Error('更新用户信息时缺少用户ID')
    }
    return request.put<UserInfo>(`/users/${data.id}`, data)
  },

  /** 用户登出 */
  async logout() {
    try {
      await request.post('/auth/logout')
    } catch {
      // 即使服务端登出失败，也清理本地状态
    } finally {
      // 清理本地存储的 token 和用户信息
      localStorage.removeItem('oat_token')
      localStorage.removeItem('oat_user')
      localStorage.removeItem('oat_remember')
    }
  }
}
