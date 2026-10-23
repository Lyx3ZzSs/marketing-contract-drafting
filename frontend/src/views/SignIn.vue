<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FileText, LogIn } from '@lucide/vue'
import { auth, completeLogin, login, logout, safeReturnPath } from '@/lib/auth'

const route = useRoute()
const router = useRouter()
const busy = ref(false)
const error = ref('')
async function signIn() {
  busy.value = true
  error.value = ''
  try { await login(route.query.returnTo) }
  catch (e) { error.value = e instanceof Error ? e.message : '登录失败，请重试'; busy.value = false }
}
onMounted(async () => {
  if (route.path === '/forbidden' || auth.error) return
  if (route.path !== '/callback') {
    if (auth.identity) await router.replace(safeReturnPath(route.query.returnTo))
    else await signIn()
    return
  }
  busy.value = true
  try { await router.replace(await completeLogin()) }
  catch (e) {
    error.value = e instanceof Error ? e.message : '登录回调验证失败，请重新登录'
    // Never leave a spent authorization code in the address bar or history.
    window.history.replaceState(null, '', '/login')
    busy.value = false
  }
})
</script>

<template>
  <main class="auth-page">
    <section v-if="error || auth.error || route.path === '/forbidden'" class="auth-card">
      <FileText :size="36" aria-hidden="true" />
      <p class="auth-company">国能日新科技股份有限公司</p>
      <h1>营销合同起草系统</h1>
      <p v-if="route.path === '/forbidden'">当前账号没有此页面的访问权限。</p>
      <p v-else>暂时无法完成统一身份认证。</p>
      <p v-if="error || auth.error" class="auth-error" role="alert">{{ error || auth.error }}</p>
      <template v-if="route.path === '/forbidden'">
        <RouterLink to="/">返回合同起草</RouterLink>
        <button type="button" @click="logout">退出登录</button>
      </template>
      <button v-else-if="!auth.error" type="button" :disabled="busy" @click="signIn">
        <LogIn :size="18" />{{ busy ? '正在跳转…' : '重新登录' }}
      </button>
      <button v-if="auth.hasSession && !auth.identity" type="button" class="auth-secondary" @click="logout">退出当前认证账号</button>
      <button v-if="auth.error" type="button" class="auth-secondary" @click="router.go(0)">重新连接</button>
    </section>
    <p v-else class="auth-redirect" role="status">{{ route.path === '/callback' ? '正在验证登录…' : '正在跳转至统一认证平台…' }}</p>
  </main>
</template>
