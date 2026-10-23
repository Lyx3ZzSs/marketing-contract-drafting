import { auth, initializeAuth, isAdmin } from './lib/auth'
import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/SignIn.vue'), meta: { public: true } },
    { path: '/callback', component: () => import('./views/SignIn.vue'), meta: { public: true } },
    { path: '/forbidden', component: () => import('./views/SignIn.vue') },
    { path: '/admin/templates', component: () => import('./views/TemplateManagement.vue') },
    { path: '/admin/templates/:id/preview', redirect: '/admin/templates' },
    { path: '/', component: () => import('./views/ContractShell.vue') },
    {
      path: '/dev',
      component: () => import('./views/DevLayout.vue'),
      children: [
        { path: '', component: () => import('./views/Workbench.vue') },
        { path: 'connections', component: () => import('./views/Connections.vue') },
      ],
    },
    { path: '/connections', redirect: '/dev/connections' },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  await initializeAuth()
  if (to.meta.public) return true
  if (!auth.identity) return { path: '/login', query: { returnTo: to.fullPath } }
  if ((to.path.startsWith('/admin/') || to.path.startsWith('/dev')) && !isAdmin.value) return '/forbidden'
  return true
})
