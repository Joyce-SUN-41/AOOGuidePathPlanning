import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { UserRole } from '@/types'

// 懒加载页面组件
const AppLayout = () => import('@/layouts/AppLayout.vue')
const LoginView = () => import('@/views/LoginView.vue')
const RegisterView = () => import('@/views/RegisterView.vue')
const HomeView = () => import('@/views/HomeView.vue')
const CehuiView = () => import('@/views/CehuiView.vue')
const PathView = () => import('@/views/PathView.vue')
const ChatView = () => import('@/views/ChatView.vue')
const DashboardView = () => import('@/views/DashboardView.vue')
const TeacherDashboardView = () => import('@/views/TeacherDashboardView.vue')
const TeacherKnowledgeView = () => import('@/views/TeacherKnowledgeView.vue')
const TeacherQuestionsView = () => import('@/views/TeacherQuestionsView.vue')
const AboutView = () => import('@/views/AboutView.vue')
const RecordsView = () => import('@/views/RecordsView.vue')
const ProfileView = () => import('@/views/ProfileView.vue')
const NotFoundView = () => import('@/views/NotFoundView.vue')

/**
 * 路由配置
 *
 * 结构说明：
 * - /login, /register — 独立页面，无布局
 * - / — AppLayout 包裹的业务页面
 *   - /           首页（项目介绍 + 快速入口）
 *   - /cehui   学情测绘（学生）
 *   - /path       我的路径（学生）
 *   - /chat       导学终端（学生）
 *   - /dashboard  学情看板（学生）
 *   - /teacher    教师仪表盘（教师）
 * - /:pathMatch(.*)* — 404
 */
const routes: RouteRecordRaw[] = [
  // ========== 认证页面（独立布局） ==========
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: {
      title: '登录',
      hidden: true
    }
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterView,
    meta: {
      title: '注册',
      hidden: true
    }
  },

  // ========== 业务页面（AppLayout） ==========
  {
    path: '/',
    component: AppLayout,
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'Home',
        component: HomeView,
        meta: {
          title: '首页',
          icon: 'HomeOutlined'
        }
      },
      {
        path: 'cehui',
        name: 'Cehui',
        component: CehuiView,
        meta: {
          title: '学情测绘',
          icon: 'ExperimentOutlined',
          roles: ['student']
        }
      },
      {
        path: 'path',
        name: 'Path',
        component: PathView,
        meta: {
          title: '我的路径',
          icon: 'NodeIndexOutlined',
          roles: ['student']
        }
      },
      {
        path: 'chat',
        name: 'Chat',
        component: ChatView,
        meta: {
          title: '导学终端',
          icon: 'RobotOutlined',
          roles: ['student']
        }
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: DashboardView,
        meta: {
          title: '学情看板',
          icon: 'DashboardOutlined',
          roles: ['student']
        }
      },
      {
        path: 'teacher',
        name: 'TeacherDashboard',
        component: TeacherDashboardView,
        meta: {
          title: '教师仪表盘',
          icon: 'TeamOutlined',
          roles: ['teacher']
        }
      },
      {
        path: 'teacher/knowledge',
        name: 'TeacherKnowledge',
        component: TeacherKnowledgeView,
        meta: {
          title: '知识点管理',
          icon: 'ApartmentOutlined',
          roles: ['teacher']
        }
      },
      {
        path: 'teacher/questions',
        name: 'TeacherQuestions',
        component: TeacherQuestionsView,
        meta: {
          title: '题库管理',
          icon: 'FileTextOutlined',
          roles: ['teacher']
        }
      },
      {
        path: 'about',
        name: 'About',
        component: AboutView,
        meta: {
          title: '关于',
          icon: 'InfoCircleOutlined'
        }
      },
      {
        path: 'records',
        name: 'Records',
        component: RecordsView,
        meta: {
          title: '我的记录',
          icon: 'HistoryOutlined',
          roles: ['student']
        }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: ProfileView,
        meta: {
          title: '个人中心',
          icon: 'IdcardOutlined',
          // 学生与教师均可访问，不在顶部导航中展示
          hidden: true
        }
      }
    ]
  },

  // ========== 404 ==========
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: NotFoundView,
    meta: {
      title: '404',
      hidden: true
    }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

// ========== 路由守卫 ==========

/** 免登录白名单 */
const WHITE_LIST = ['/login', '/register']

router.beforeEach((to, _from, next) => {
  // 设置页面标题
  const title = to.meta['title'] as string
  document.title = title ? `${title} - 动麦智导` : '动麦智导'

  // 白名单页面直接放行
  if (WHITE_LIST.includes(to.path)) {
    // 已登录用户访问登录/注册页 → 重定向到首页
    const userStore = useUserStore()
    if (userStore.isAuthenticated && WHITE_LIST.includes(to.path)) {
      next({ path: '/home', replace: true })
      return
    }
    next()
    return
  }

  // 需要认证的页面
  const userStore = useUserStore()

  // pinia-plugin-persistedstate 已自动从 localStorage 恢复登录态
  // 无需手动调用 restoreLogin()
  if (!userStore.isAuthenticated) {
    // 未登录 → 跳转登录页，带上 redirect 参数
    next({
      path: '/login',
      query: { redirect: to.fullPath },
      replace: true
    })
    return
  }

  // 角色权限检查
  const requiredRoles = (to.meta['roles'] as UserRole[] | undefined) || []
  if (requiredRoles.length > 0) {
    const userRole = userStore.role
    if (!userRole || !requiredRoles.includes(userRole)) {
      // 无权限 → 返回首页
      console.warn(`[Router Guard] 用户角色 "${userRole}" 无权访问 "${to.path}"`)
      next({ path: '/home', replace: true })
      return
    }
  }

  next()
})

export default router
