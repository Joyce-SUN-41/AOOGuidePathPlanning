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
  logout() {
    return Promise.resolve()
  }
}
