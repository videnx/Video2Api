<template>
  <div class="app-shell">
    <template v-if="isLoginPage">
      <router-view />
    </template>
    <template v-else>
      <aside class="sidebar">
        <div class="brand">Video2Api</div>
        <button class="menu-item" :class="{ active: route.path === '/ixbrowser-groups' }" @click="go('/ixbrowser-groups')">
          ixBrowser 管理
        </button>
      </aside>
      <main class="main">
        <header class="topbar">
          <span class="user">{{ currentUser?.username || '-' }}</span>
          <button class="logout" @click="logout">退出</button>
        </header>
        <div class="content">
          <router-view />
        </div>
      </main>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isLoginPage = computed(() => route.path === '/login')
const currentUser = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}')
  } catch {
    return null
  }
})

const go = (path) => router.push(path)

const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  router.push('/login')
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  background: linear-gradient(180deg, #f5f8ff 0%, #f8fafc 100%);
}

.sidebar {
  width: 220px;
  background: #0f172a;
  color: #fff;
  padding: 20px 12px;
}

.brand {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 20px;
  padding: 0 8px;
}

.menu-item {
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: #cbd5e1;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
}

.menu-item.active,
.menu-item:hover {
  background: #1e293b;
  color: #fff;
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: 56px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  padding: 0 20px;
}

.user {
  color: #0f172a;
  font-weight: 600;
}

.logout {
  border: 1px solid #cbd5e1;
  background: #fff;
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
}

.content {
  flex: 1;
  overflow: auto;
}
</style>
