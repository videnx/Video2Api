<template>
  <div class="login-wrap">
    <div class="login-card">
      <h1>Video2Api</h1>
      <p>默认账号密码：Admin / Admin</p>
      <el-form @submit.prevent>
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" style="width: 100%" @click="doLogin">登录</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api'

const router = useRouter()
const username = ref('Admin')
const password = ref('Admin')
const loading = ref(false)

const doLogin = async () => {
  loading.value = true
  try {
    const data = await login(username.value, password.value)
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user || {}))
    ElMessage.success('登录成功')
    router.push('/ixbrowser-groups')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  width: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top left, #dbeafe 0%, #f8fafc 55%);
}

.login-card {
  width: 360px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.12);
  padding: 24px;
}

h1 {
  margin: 0;
  font-size: 26px;
  color: #0f172a;
}

p {
  margin: 8px 0 18px;
  color: #64748b;
  font-size: 12px;
}
</style>
