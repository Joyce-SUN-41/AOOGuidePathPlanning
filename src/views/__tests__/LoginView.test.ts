import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LoginView from '@/views/LoginView.vue'
import { useUserStore } from '@/stores/user'

// ── Mock 外部依赖，避免真实网络/路由副作用 ──
// 注意：vi.mock 工厂会被 hoist 到顶部，工厂内引用的变量必须用 vi.hoisted 声明，
// 否则 Hoisting 后捕获的是 undefined。
const { pushSpy, loginMock } = vi.hoisted(() => ({
  pushSpy: vi.fn(),
  loginMock: vi.fn(),
}))
vi.mock('vue-router', () => ({
  // 登录页的认证序列除了 push，还会用 resolve 预校验目标路由是否可达，
  // 这里返回一个已匹配的结果，代表路由存在。
  useRouter: () => ({
    push: pushSpy,
    resolve: (to: string) => ({ matched: [{ path: to }] }),
  }),
  useRoute: () => ({ query: {} }),
}))

// 仅 mock authApi.login，保留 userStore 的真实逻辑
vi.mock('@/api/modules/auth', () => ({
  authApi: {
    login: (...args: unknown[]) => loginMock(...args),
  },
}))

// 避免 ant-design-vue message 在 jsdom 中打印噪声（行为不变）
vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<typeof import('ant-design-vue')>('ant-design-vue')
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    },
  }
})

const mockUser = {
  id: 'u1',
  username: 'tester',
  nickname: '测试员',
  avatar: null,
  email: null,
  phone: null,
  role: 'student' as const,
  status: 1 as const,
  createTime: '2026-01-01T00:00:00Z',
}

/**
 * 认证仪式是分阶段异步序列（塌缩 → 逐行日志 → 收敛），中间存在真实定时器间隔。
 * 对于「点击触发、不返回 Promise」的场景，需要等待序列走完再断言。
 */
async function flushSequence(): Promise<void> {
  for (let i = 0; i < 12; i++) {
    await new Promise((r) => setTimeout(r, 60))
    await flushPromises()
  }
}

describe('LoginView 登录流程', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    pushSpy.mockClear()
    loginMock.mockReset()
    // 默认登录成功
    loginMock.mockResolvedValue({
      token: 'fake-token',
      userInfo: mockUser,
      refreshToken: 'fake-refresh',
    })
  })

  it('渲染登录表单（用户名/密码输入框 + 登录按钮）', () => {
    const wrapper = mount(LoginView, { global: { stubs: { OatDispersalBackground: true } } })
    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).toContain('登录')
  })

  it('表单未填写时提交被校验拦截，不调用 login', async () => {
    const wrapper = mount(LoginView, { global: { stubs: { OatDispersalBackground: true } } })
    const vm = wrapper.vm as unknown as {
      formRef: { validate: () => Promise<void> } | undefined
      handleLogin: () => Promise<void>
    }
    // 模拟 a-form validate 失败（必填未填）
    vi.spyOn(vm, 'formRef', 'get').mockReturnValue({
      validate: () => Promise.reject(new Error('validation failed')),
    } as never)
    await vm.handleLogin()
    await flushPromises()
    expect(loginMock).not.toHaveBeenCalled()
    expect(pushSpy).not.toHaveBeenCalled()
  })

  it('登录成功后调用 store.login 并跳转到默认首页 /home', async () => {
    const wrapper = mount(LoginView, { global: { stubs: { OatDispersalBackground: true } } })
    const vm = wrapper.vm as unknown as {
      formState: { username: string; password: string; remember: boolean }
      handleLogin: () => Promise<void>
    }
    vm.formState.username = 'tester'
    vm.formState.password = '123456'
    // 认证仪式为分阶段异步序列，需等待其完整走完
    await vm.handleLogin()
    await flushPromises()

    expect(loginMock).toHaveBeenCalledTimes(1)
    expect(loginMock).toHaveBeenCalledWith(
      expect.objectContaining({ username: 'tester', password: '123456' })
    )
    // 成功后跳转默认首页（route.query.redirect 为空时）
    expect(pushSpy).toHaveBeenCalledWith('/home')
  })

  it('登录失败后停留在登录页且不跳转', async () => {
    const wrapper = mount(LoginView, { global: { stubs: { OatDispersalBackground: true } } })
    // 直接 spy store.login 返回 false，确定性验证失败分支
    const store = useUserStore()
    vi.spyOn(store, 'login').mockResolvedValue(false)
    const vm = wrapper.vm as unknown as {
      formState: { username: string; password: string; remember: boolean }
      handleLogin: () => Promise<void>
    }
    vm.formState.username = 'tester'
    vm.formState.password = '123456'
    await vm.handleLogin()
    await flushPromises()

    expect(store.login).toHaveBeenCalledTimes(1)
    // 失败时不应跳转
    expect(pushSpy).not.toHaveBeenCalled()
  })

  it('demo 登录按钮会预填账号并触发登录', async () => {
    const wrapper = mount(LoginView, { global: { stubs: { OatDispersalBackground: true } } })
    const studentBtn = wrapper.find('.demo-btn--student')
    expect(studentBtn.exists()).toBe(true)
    await studentBtn.trigger('click')
    // demo 登录为 fire-and-forget，需等待认证序列完整走完
    await flushSequence()

    expect(loginMock).toHaveBeenCalledTimes(1)
    expect(loginMock).toHaveBeenCalledWith(
      expect.objectContaining({ username: 'student_demo', password: '123456' })
    )
  })
})
