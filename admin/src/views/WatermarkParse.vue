<template>
  <div class="watermark-parse-page">
    <section class="command-bar">
      <div class="command-left">
        <div class="command-title">去水印解析</div>
        <div class="panel-subtitle">输入 Sora 分享链接，获取可直接访问的无水印链接。</div>
      </div>
    </section>

    <el-card class="table-card">
      <template #header>
        <div class="table-head stack">
          <span>分享链接解析</span>
          <span class="table-hint">严格按系统配置的解析方式执行（custom / third_party）</span>
        </div>
      </template>

      <el-form label-width="110px" @submit.prevent>
        <el-form-item label="分享链接">
          <el-input
            v-model="form.share_url"
            clearable
            placeholder="例如：https://sora.chatgpt.com/p/s_xxxxxxxx"
            @keyup.enter="handleParse"
          />
        </el-form-item>
        <el-form-item>
          <div class="action-row">
            <el-button type="primary" :loading="parsing" @click="handleParse">解析去水印链接</el-button>
            <el-button :disabled="parsing" @click="handleReset">重置</el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="result" class="table-card">
      <template #header>
        <div class="table-head">
          <span>解析结果</span>
        </div>
      </template>
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">Share ID</span>
          <strong class="mono">{{ result.share_id }}</strong>
        </div>
        <div class="result-item">
          <span class="result-label">解析方式</span>
          <strong>{{ result.parse_method }}</strong>
        </div>
        <div class="result-item">
          <span class="result-label">标准分享链接</span>
          <strong class="link-wrap">{{ result.share_url }}</strong>
        </div>
        <div class="result-item">
          <span class="result-label">无水印链接</span>
          <div class="result-link-row">
            <a class="result-link" href="#" @click.prevent="openLink(result.watermark_url)">
              {{ result.watermark_url }}
            </a>
            <el-button size="small" class="btn-soft" @click="copyLink(result.watermark_url)">复制</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <el-alert
      v-if="errorText"
      class="error-alert"
      type="error"
      :closable="false"
      :title="errorText"
      show-icon
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { parseSoraWatermarkLink } from '../api'

const parsing = ref(false)
const errorText = ref('')
const result = ref(null)
const form = ref({
  share_url: ''
})

const copyText = async (text) => {
  const value = String(text || '')
  if (!value) return false
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return true
  }
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(textarea)
  return ok
}

const handleParse = async () => {
  const shareUrl = String(form.value.share_url || '').trim()
  if (!shareUrl) {
    ElMessage.warning('请先输入 Sora 分享链接')
    return
  }
  parsing.value = true
  errorText.value = ''
  try {
    const data = await parseSoraWatermarkLink({ share_url: shareUrl })
    result.value = data || null
    ElMessage.success('解析成功')
  } catch (error) {
    result.value = null
    errorText.value = error?.response?.data?.detail || '解析失败'
  } finally {
    parsing.value = false
  }
}

const handleReset = () => {
  form.value.share_url = ''
  result.value = null
  errorText.value = ''
}

const openLink = (url) => {
  if (!url) return
  window.open(url, '_blank', 'noopener')
}

const copyLink = async (url) => {
  if (!url) return
  try {
    const ok = await copyText(url)
    if (!ok) {
      ElMessage.error('复制失败，请手动复制')
      return
    }
    ElMessage.success('链接已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}
</script>

<style scoped>
.watermark-parse-page {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--page-gap);
}

.action-row {
  display: flex;
  gap: 10px;
}

.result-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-label {
  font-size: 12px;
  color: var(--muted);
}

.result-link-row {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.result-link {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--accent-strong);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-link:hover {
  text-decoration: underline;
}

.link-wrap {
  word-break: break-all;
  font-size: 13px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
}

.error-alert {
  border-radius: var(--radius-md);
}

@media (max-width: 960px) {
  .result-link-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
