<script setup lang="ts">
import { FileText, PanelsTopLeft, Cable, ArrowUpRight } from '@lucide/vue'
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink to="/dev" class="brand"><span class="brand-icon"><FileText :size="21" /></span><span>合同起草<span class="brand-subtitle">CONTRACT STUDIO</span></span></RouterLink>
      <div class="sidebar-label">工作空间</div>
      <nav aria-label="主导航">
        <RouterLink to="/dev" class="nav-link" exact-active-class="active"><PanelsTopLeft :size="17" />开发工作台<span class="nav-number">01</span></RouterLink>
        <RouterLink to="/dev/connections" class="nav-link" active-class="active"><Cable :size="17" />服务连接<span class="nav-number">02</span></RouterLink>
      </nav>
      <div class="sidebar-foot">
        <div class="flex items-center gap-2 text-xs font-medium"><span class="status-dot"></span>本地开发环境</div>
        <p>基础链路验证 · v0.1.0</p>
        <a href="/api/docs" class="mt-3 flex items-center gap-1 text-xs" target="_blank" rel="noopener">接口文档<ArrowUpRight :size="13" /></a>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar"><span>营销业务 / <strong>合同起草</strong></span><div class="flex items-center gap-3"><span class="environment-label">DEVELOPMENT</span><span class="avatar">研</span></div></header>
      <main><RouterView /></main>
    </div>
  </div>
</template>
