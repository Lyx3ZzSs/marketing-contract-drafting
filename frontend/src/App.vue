<script setup lang="ts">
import { auth, logout } from '@/lib/auth'
import '@/styles/auth.css'
</script>

<template>
  <div v-if="auth.identity" class="account-bar">
    <span>{{ auth.identity.name || auth.identity.username }}</span>
    <span v-if="auth.identity.department_name">{{ auth.identity.department_name }}</span>
    <button type="button" @click="logout">退出登录</button>
  </div>
  <RouterView v-if="auth.identity || $route.meta.public" :key="$route.path" />
</template>
