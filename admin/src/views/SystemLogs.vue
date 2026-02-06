<template>
  <div class="logs-page">
    <section class="command-bar" v-loading="loading">
      <div class="command-left">
        <div class="brand">
          <div class="title">日志中心</div>
          <div class="subtitle">审计 · API · 任务事件</div>
        </div>
        <div class="filters">
          <el-select v-model="filters.type" class="w-140" @change="loadLogs">
            <el-option label="全部" value="all" />
            <el-option label="审计" value="audit" />
            <el-option label="API" value="api" />
            <el-option label="任务事件" value="task" />
          </el-select>

          <el-select v-model="filters.status" class="w-140" clearable @change="loadLogs">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>

          <el-select v-model="filters.level" class="w-140" clearable @change="loadLogs">
            <el-option label="INFO" value="INFO" />
            <el-option label="WARN" value="WARN" />
            <el-option label="ERROR" value="ERROR" />
          </el-select>

          <el-input v-model="filters.keyword" class="w-260" clearable placeholder="关键词" />
          <el-input v-model="filters.user" class="w-180" clearable placeholder="用户名" />

          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            @change="loadLogs"
          />
        </div>
      </div>

      <div class="command-right">
        <div class="actions">
          <el-button @click="resetFilters">重置</el-button>
          <el-button type="primary" @click="loadLogs">刷新</el-button>
        </div>
      </div>
    </section>

    <el-card class="table-card" v-loading="loading">
      <template #header>
        <div class="table-head">
          <span>日志列表</span>
          <span class="table-hint">仅保留最近 {{ retentionDays }} 天</span>
        </div>
      </template>

      <el-table :data="logs" class="card-table" empty-text="暂无日志">
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.type)">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="动作" min-width="160" />
        <el-table-column prop="operator_username" label="用户" width="120" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.status" size="small" :type="statusTag(row.status)">{{ row.status }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" width="110">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column prop="message" label="消息" min-width="240" />
        <el-table-column label="详情" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" title="日志详情" size="520px" direction="rtl">
      <div v-if="detailRow" class="detail">
        <div class="detail-grid">
          <div class="detail-item"><span>类型</span><strong>{{ detailRow.type }}</strong></div>
          <div class="detail-item"><span>动作</span><strong>{{ detailRow.action }}</strong></div>
          <div class="detail-item"><span>用户</span><strong>{{ detailRow.operator_username || '-' }}</strong></div>
          <div class="detail-item"><span>状态</span><strong>{{ detailRow.status || '-' }}</strong></div>
          <div class="detail-item"><span>等级</span><strong>{{ detailRow.level || '-' }}</strong></div>
          <div class="detail-item"><span>时间</span><strong>{{ formatTime(detailRow.created_at) }}</strong></div>
        </div>
        <div class="detail-label">消息</div>
        <div class="detail-text">{{ detailRow.message || '-' }}</div>

        <div class="detail-label">Metadata</div>
        <pre class="detail-json">{{ formatJson(detailRow.metadata) }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSystemSettings, listSystemLogs } from '../api'

const loading = ref(false)
const logs = ref([])
const detailVisible = ref(false)
const detailRow = ref(null)
const retentionDays = ref(3)

const filters = ref({
  type: 'all',
  status: '',
  level: '',
  keyword: '',
  user: '',
  limit: 200
})

const timeRange = ref([])

const initRange = () => {
  const end = new Date()
  const start = new Date(end.getTime() - 3 * 24 * 60 * 60 * 1000)
  timeRange.value = [start, end]
}

const buildParams = () => {
  const params = {
    type: filters.value.type,
    limit: filters.value.limit
  }
  if (filters.value.status) params.status = filters.value.status
  if (filters.value.level) params.level = filters.value.level
  if (filters.value.keyword) params.keyword = filters.value.keyword
  if (filters.value.user) params.user = filters.value.user
  if (Array.isArray(timeRange.value) && timeRange.value.length === 2) {
    const [start, end] = timeRange.value
    if (start) params.start_at = new Date(start).toISOString()
    if (end) params.end_at = new Date(end).toISOString()
  }
  return params
}

const loadLogs = async () => {
  loading.value = true
  try {
    const data = await listSystemLogs(buildParams())
    logs.value = Array.isArray(data) ? data : []
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '读取日志失败')
  } finally {
    loading.value = false
  }
}

const loadSystemSettings = async () => {
  try {
    const envelope = await getSystemSettings()
    const days = envelope?.data?.logging?.audit_log_retention_days
    if (typeof days === 'number' && !Number.isNaN(days)) {
      retentionDays.value = days
    }
  } catch {
    retentionDays.value = 3
  }
}

const resetFilters = () => {
  filters.value = {
    type: 'all',
    status: '',
    level: '',
    keyword: '',
    user: '',
    limit: 200
  }
  initRange()
  loadLogs()
}

const openDetail = (row) => {
  detailRow.value = row
  detailVisible.value = true
}

const formatTime = (value) => {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

const formatDuration = (value) => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return '-'
  return `${num} ms`
}

const formatJson = (value) => {
  if (!value) return '-'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const statusTag = (status) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

const typeTag = (type) => {
  if (type === 'audit') return 'success'
  if (type === 'api') return 'info'
  if (type === 'task') return 'warning'
  return 'primary'
}

onMounted(() => {
  loadSystemSettings()
  initRange()
  loadLogs()
})
</script>

<style scoped>
.logs-page {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--page-gap);
}

.brand .title {
  font-size: 20px;
  font-weight: 700;
}

.detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.detail-item {
  background: rgba(15, 23, 42, 0.04);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  font-size: 12px;
  color: var(--muted);
}

.detail-item strong {
  display: block;
  color: var(--ink);
  font-size: 14px;
  margin-top: 4px;
}

.detail-label {
  font-size: 12px;
  color: var(--muted);
}

.detail-text {
  background: var(--card-strong);
  border-radius: var(--radius-md);
  padding: 12px;
  border: 1px solid var(--border);
  font-size: 13px;
}

.detail-json {
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 12px;
  font-size: 12px;
  max-height: 420px;
  overflow: auto;
}

.w-140 {
  width: 140px;
}

.w-180 {
  width: 180px;
}

.w-260 {
  width: 260px;
}

@media (max-width: 980px) {
  .command-bar {
    flex-direction: column;
    align-items: flex-start;
  }
  .command-right {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
