import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import IxBrowserGroups from '../views/IxBrowserGroups.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login, meta: { public: true } },
    { path: '/', redirect: '/ixbrowser-groups' },
    { path: '/ixbrowser-groups', component: IxBrowserGroups }
  ]
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.public) {
    if (token && to.path === '/login') {
      next('/ixbrowser-groups')
      return
    }
    next()
    return
  }

  if (!token) {
    next('/login')
    return
  }

  next()
})

export default router
