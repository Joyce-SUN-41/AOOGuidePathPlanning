import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo, UserRole, LoginParams, RegisterParams } from '@/types'
import { authApi } from '@/api/modules/auth'
import { message } from 'ant-design-vue'
import { trackEvent } from '@/utils/tracking'

/**
 * 用户认证与信息状态管理
 *
 * 特性：
 * - pinia-plugin-persistedstate 自动持久化 token / userInfo
 * - 记住登录状态（remember 控制刷新后是否清除 token）
 * - 角色判断与权限校验
 * - 自动从 API 刷新用户信息
 */
export const useUserStore = defineStore(
  'user',
  () => {
    // ═══════════ State ═══════════

    /** JWT 令牌 */
    const token = ref<string>('')

    /** 刷新令牌 (用于 access token 过期时静默续期) */
    const refreshToken = ref<string>('')

    /** 用户信息 */
    const userInfo = ref<UserInfo | null>(null)

    /** 是否勾选"记住我" */
    const remember = ref<boolean>(false)

    /** 是否正在加载用户信息 */
    const _loading = ref(false)

    // ═══════════ Getters ═══════════

    /** 是否已认证（等价于已登录） */
    const isAuthenticated = computed(() => !!token.value)

    /** 当前用户角色 */
    const role = computed<UserRole | null>(() => userInfo.value?.role ?? null)

    /** 是否为教师 */
    const isTeacher = computed(() => role.value === 'teacher')

    /** 是否为学生 */
    const isStudent = computed(() => role.value === 'student')

    /** 用户显示名称 */
    const displayName = computed(
      () => userInfo.value?.nickname || userInfo.value?.username || '未登录'
    )

    /** 用户头像 */
    const avatar = computed(() => userInfo.value?.avatar || '')

    // ═══════════ Actions ═══════════

    /** 登录 */
    async function login(params: LoginParams): Promise<boolean> {
      try {
        const res = await authApi.login(params)
        token.value = res.token
        refreshToken.value = res.refreshToken ?? ''
        userInfo.value = res.userInfo
        remember.value = params.remember ?? false
        trackEvent('user_login', { role: res.userInfo?.role ?? '', success: true })
        message.success('登录成功，欢迎回来！')
        return true
      } catch {
        trackEvent('user_login', { success: false })
        return false
      }
    }

    /** 注册 */
    async function register(params: RegisterParams): Promise<boolean> {
      try {
        const res = await authApi.register(params)
        token.value = res.token
        refreshToken.value = res.refreshToken ?? ''
        userInfo.value = res.userInfo
        remember.value = false
        trackEvent('user_register', { role: res.userInfo?.role ?? '', success: true })
        message.success('注册成功！')
        return true
      } catch {
        trackEvent('user_register', { success: false })
        return false
      }
    }

    /** 退出登录 */
    function logout(showMessage = true): void {
      trackEvent('user_logout', { role: userInfo.value?.role ?? '' })
      token.value = ''
      refreshToken.value = ''
      userInfo.value = null
      // 立即清除所有认证相关的 localStorage 条目，避免 persist 插件恢复
      localStorage.removeItem('oat_token')
      localStorage.removeItem('oat_user')
      localStorage.removeItem('oat_user_store')
      if (showMessage) {
        message.info('已退出登录')
      }
    }

    /** 从 API 获取最新用户信息 */
    async function fetchUserInfo(): Promise<void> {
      if (!token.value) return

      _loading.value = true
      try {
        // 通过获取当前用户接口刷新信息
        const { userApi } = await import('@/api/modules/user')
        const info = await userApi.getUserInfo()
        // 保留本地已有的 avatar/phone，防止后端未返回时被清空
        const oldAvatar = userInfo.value?.avatar
        const oldPhone = userInfo.value?.phone
        userInfo.value = info
        if (oldAvatar && !userInfo.value?.avatar) {
          userInfo.value.avatar = oldAvatar
        }
        if (oldPhone && !userInfo.value?.phone) {
          userInfo.value.phone = oldPhone
        }
      } catch {
        // 获取失败时不清除现有数据；可能仅网络问题
        console.warn('[UserStore] 获取用户信息失败，保留缓存数据')
      } finally {
        _loading.value = false
      }
    }

    /** 手动设置 token（用于刷新 token 后更新） */
    function setToken(newToken: string): void {
      token.value = newToken
    }

    /** 刷新 token 后更新 access + refresh 令牌对 */
    function setTokens(newToken: string, newRefreshToken?: string): void {
      token.value = newToken
      if (newRefreshToken) {
        refreshToken.value = newRefreshToken
      }
    }

    /** 更新用户部分信息 */
    function updateUserInfo(info: Partial<UserInfo>): void {
      if (userInfo.value) {
        userInfo.value = { ...userInfo.value, ...info }
      }
    }

    /** 同步资料到服务端 */
    async function syncProfileToServer(profile: Partial<UserInfo>): Promise<boolean> {
      if (!token.value) return false
      try {
        const { userApi } = await import('@/api/modules/user')
        const result = await userApi.updateProfile(profile)
        // 用服务端返回的完整信息更新本地
        userInfo.value = result
        return true
      } catch {
        return false
      }
    }

    return {
      // State
      token,
      refreshToken,
      userInfo,
      remember,
      _loading,
      // Getters
      isAuthenticated,
      role,
      isTeacher,
      isStudent,
      displayName,
      avatar,
      // Actions
      login,
      register,
      logout,
      fetchUserInfo,
      setToken,
      setTokens,
      updateUserInfo,
      syncProfileToServer
    }
  },
  {
    persist: {
      key: 'oat_user_store',
      storage: localStorage,
      // 仅持久化 token / refreshToken / userInfo / remember (v3 使用 paths 字段)
      paths: ['token', 'refreshToken', 'userInfo', 'remember'],
      // 退出登录后清空 storage
      afterRestore(ctx) {
        // 如果没有勾选"记住我"，退出时不保留 token
        // 此逻辑在路由守卫中通过 restoreLogin 处理
        void ctx
      }
    }
  }
)
