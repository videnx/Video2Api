<template>
  <div class="ix-page">
    <section class="hero">
      <div>
        <h2 class="hero-title">ixBrowser 分组与 Sora 自动化</h2>
        <p class="hero-subtitle">支持账号扫描、历史回填、单窗口文生视频与任务状态监听。</p>
      </div>
      <div class="hero-actions">
        <el-select v-model="selectedGroupTitle" size="large" class="group-select" @change="onGroupChange">
          <el-option
            v-for="group in groups"
            :key="group.id"
            :label="`${group.title} (ID:${group.id})`"
            :value="group.title"
          />
        </el-select>
        <el-button size="large" @click="refreshAll" :loading="latestLoading || historyLoading || generateJobsLoading">
          刷新
        </el-button>
        <el-button size="large" type="warning" :loading="scanLoading" @click="scanNow">
          扫描账号与次数
        </el-button>
      </div>
    </section>

    <section class="metrics-grid">
      <article class="metric-card">
        <span class="metric-label">窗口总数</span>
        <strong class="metric-value">{{ metrics.total }}</strong>
      </article>
      <article class="metric-card success">
        <span class="metric-label">本次成功</span>
        <strong class="metric-value">{{ metrics.success }}</strong>
      </article>
      <article class="metric-card danger">
        <span class="metric-label">本次失败</span>
        <strong class="metric-value">{{ metrics.failed }}</strong>
      </article>
      <article class="metric-card warning">
        <span class="metric-label">回填条数</span>
        <strong class="metric-value">{{ metrics.fallback }}</strong>
      </article>
    </section>

    <section class="content-grid">
      <div class="left-column">
        <el-card class="panel groups-panel" v-loading="groupsLoading">
          <template #header>
            <div class="panel-header">
              <span>分组列表</span>
              <el-button text @click="loadGroups">刷新</el-button>
            </div>
          </template>
          <el-scrollbar height="260px">
            <div
              v-for="group in groups"
              :key="group.id"
              class="group-item"
              :class="{ active: selectedGroupTitle === group.title }"
              @click="selectGroup(group.title)"
            >
              <div>
                <div class="group-name">{{ group.title }}</div>
                <div class="group-meta">ID: {{ group.id }}</div>
              </div>
              <el-tag size="small" type="success">{{ group.window_count }} 窗口</el-tag>
            </div>
            <el-empty v-if="groups.length === 0" description="暂无分组" :image-size="70" />
          </el-scrollbar>
        </el-card>

        <el-card class="panel history-panel" v-loading="historyLoading">
          <template #header>
            <div class="panel-header">
              <span>扫描历史（最近10次）</span>
              <el-button text @click="loadHistory">刷新</el-button>
            </div>
          </template>
          <el-scrollbar height="330px">
            <div
              v-for="run in historyRuns"
              :key="run.run_id"
              class="history-item"
              :class="{ active: activeRunId === run.run_id }"
              @click="openRun(run.run_id)"
            >
              <div class="history-top">
                <span>Run #{{ run.run_id }}</span>
                <small>{{ formatTime(run.scanned_at) }}</small>
              </div>
              <div class="history-stats">
                <el-tag size="small">总 {{ run.total_windows }}</el-tag>
                <el-tag size="small" type="success">成 {{ run.success_count }}</el-tag>
                <el-tag size="small" type="danger">败 {{ run.failed_count }}</el-tag>
              </div>
            </div>
            <el-empty v-if="historyRuns.length === 0" description="暂无历史" :image-size="70" />
          </el-scrollbar>
        </el-card>
      </div>

      <div class="right-column">
        <el-card class="panel windows-panel" v-loading="groupsLoading">
          <template #header>
            <div class="panel-header">
              <span>窗口操作（仅 Sora）</span>
              <el-tag size="small" :type="canGenerate ? 'success' : 'info'">
                {{ canGenerate ? '可生成' : '仅 Sora 分组可用' }}
              </el-tag>
            </div>
          </template>

          <el-table v-if="selectedWindows.length > 0" :data="selectedWindows" border stripe height="220" size="small">
            <el-table-column prop="profile_id" label="窗口ID" width="90" />
            <el-table-column prop="name" label="窗口名" min-width="170" />
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" :disabled="!canGenerate" @click="openGenerateDialog(row)">
                  文生视频
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="当前分组暂无窗口" :image-size="70" />
        </el-card>

        <el-card class="panel jobs-panel" v-loading="generateJobsLoading">
          <template #header>
            <div class="panel-header">
              <span>文生视频任务</span>
              <el-button text @click="loadGenerateJobs">刷新</el-button>
            </div>
          </template>

          <el-table v-if="generateJobs.length > 0" :data="generateJobs" border stripe size="small" height="250">
            <el-table-column prop="job_id" label="Job" width="72" />
            <el-table-column prop="profile_id" label="窗口" width="72" />
            <el-table-column prop="duration" label="时长" width="68" />
            <el-table-column prop="aspect_ratio" label="比例" width="92" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="jobStatusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="task_id" label="任务ID" min-width="150" />
            <el-table-column label="任务链接" min-width="170">
              <template #default="{ row }">
                <a v-if="row.task_url" :href="row.task_url" target="_blank" class="task-link">打开</a>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="error" label="错误" min-width="150">
              <template #default="{ row }">{{ row.error || '-' }}</template>
            </el-table-column>
            <el-table-column prop="elapsed_ms" label="耗时(ms)" width="90" />
          </el-table>
          <el-empty v-else description="暂无文生任务" :image-size="70" />
        </el-card>

        <el-card class="panel result-panel" v-loading="latestLoading || runLoading">
          <template #header>
            <div class="panel-header run-head">
              <div>
                <div class="run-title">{{ currentRunTitle }}</div>
                <div class="run-meta">
                  <span>分组：{{ selectedGroupTitle || '-' }}</span>
                  <span>扫描时间：{{ scanData?.scanned_at ? formatTime(scanData.scanned_at) : '-' }}</span>
                </div>
              </div>
              <el-tag v-if="scanData?.fallback_applied_count" type="warning">
                已回填 {{ scanData.fallback_applied_count }} 条
              </el-tag>
            </div>
          </template>

          <el-table v-if="scanRows.length" :data="scanRows" border stripe height="420" class="scan-table">
            <el-table-column prop="profile_id" label="窗口ID" width="90" />
            <el-table-column prop="window_name" label="窗口名" min-width="160" />
            <el-table-column prop="account" label="账号" min-width="200">
              <template #default="{ row }">{{ row.account || '-' }}</template>
            </el-table-column>
            <el-table-column prop="quota_remaining_count" label="可用次数" width="90">
              <template #default="{ row }">{{ row.quota_remaining_count ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="数据来源" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.fallback_applied ? 'warning' : 'success'">
                  {{ row.fallback_applied ? '回填' : '本次' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="session_status" label="Session" width="90" />
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.success ? 'success' : 'danger'">{{ row.success ? '成功' : '失败' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
            <el-table-column label="错误" min-width="160">
              <template #default="{ row }">{{ row.error || row.quota_error || '-' }}</template>
            </el-table-column>
            <el-table-column label="详情" fixed="right" width="86">
              <template #default="{ row }">
                <el-button size="small" @click="viewSession(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无扫描结果" :image-size="90" />
        </el-card>
      </div>
    </section>

    <el-dialog v-model="generateDialogVisible" title="Sora 文生视频" width="620px">
      <el-form :model="generateForm" label-width="86px">
        <el-form-item label="窗口ID">
          <el-input v-model="generateForm.profile_id" disabled />
        </el-form-item>
        <el-form-item label="时长">
          <el-select v-model="generateForm.duration" style="width: 100%">
            <el-option label="10秒" value="10s" />
            <el-option label="15秒" value="15s" />
            <el-option label="25秒" value="25s" />
          </el-select>
        </el-form-item>
        <el-form-item label="比例">
          <el-select v-model="generateForm.aspect_ratio" style="width: 100%">
            <el-option label="横屏 landscape" value="landscape" />
            <el-option label="竖屏 portrait" value="portrait" />
          </el-select>
        </el-form-item>
        <el-form-item label="提示词">
          <el-input
            v-model="generateForm.prompt"
            type="textarea"
            :rows="5"
            placeholder="请输入文生视频提示词"
            maxlength="4000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="generateSubmitting" @click="submitGenerateJob">开始生成</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sessionDialogVisible" title="Session / Quota 详情" width="900px">
      <pre class="session-preview">{{ currentSessionText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createIxBrowserSoraGenerateJob,
  getIxBrowserGroupWindows,
  getIxBrowserSoraGenerateJob,
  getIxBrowserSoraSessionByRun,
  getIxBrowserSoraSessionScanHistory,
  getLatestIxBrowserSoraSessionAccounts,
  listIxBrowserSoraGenerateJobs,
  scanIxBrowserSoraSessionAccounts
} from '../api'

const groupsLoading = ref(false)
const historyLoading = ref(false)
const latestLoading = ref(false)
const runLoading = ref(false)
const scanLoading = ref(false)
const generateJobsLoading = ref(false)
const generateSubmitting = ref(false)

const groups = ref([])
const historyRuns = ref([])
const selectedGroupTitle = ref('Sora')
const activeRunId = ref(null)
const scanData = ref(null)
const generateJobs = ref([])

const generateDialogVisible = ref(false)
const generateForm = ref({
  profile_id: null,
  prompt: '',
  duration: '10s',
  aspect_ratio: 'landscape'
})

const sessionDialogVisible = ref(false)
const currentSessionText = ref('')
const pollingJobId = ref(null)
let pollingTimer = null

const scanRows = computed(() => scanData.value?.results || [])
const selectedGroup = computed(() => groups.value.find((g) => g.title === selectedGroupTitle.value) || null)
const selectedWindows = computed(() => selectedGroup.value?.windows || [])
const canGenerate = computed(() => selectedGroupTitle.value === 'Sora')

const metrics = computed(() => ({
  total: scanData.value?.total_windows || 0,
  success: scanData.value?.success_count || 0,
  failed: scanData.value?.failed_count || 0,
  fallback: scanData.value?.fallback_applied_count || 0
}))

const currentRunTitle = computed(() => {
  if (!scanData.value?.run_id) return '当前结果'
  return `Run #${scanData.value.run_id} 结果`
})

const formatTime = (value) => {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

const jobStatusType = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

const stopJobPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
  pollingJobId.value = null
}

const startJobPolling = (jobId) => {
  stopJobPolling()
  pollingJobId.value = jobId
  pollingTimer = setInterval(async () => {
    try {
      const job = await getIxBrowserSoraGenerateJob(jobId)
      const index = generateJobs.value.findIndex((item) => item.job_id === job.job_id)
      if (index >= 0) {
        generateJobs.value[index] = job
      } else {
        generateJobs.value.unshift(job)
      }
      if (job.status === 'completed' || job.status === 'failed') {
        stopJobPolling()
      }
    } catch {
      stopJobPolling()
    }
  }, 6000)
}

const loadGroups = async () => {
  groupsLoading.value = true
  try {
    const data = await getIxBrowserGroupWindows()
    groups.value = Array.isArray(data) ? data : []
    const sora = groups.value.find((g) => g.title === 'Sora')
    if (sora) {
      selectedGroupTitle.value = sora.title
    } else if (!groups.value.some((g) => g.title === selectedGroupTitle.value) && groups.value.length > 0) {
      selectedGroupTitle.value = groups.value[0].title
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '获取分组失败')
  } finally {
    groupsLoading.value = false
  }
}

const loadHistory = async () => {
  if (!selectedGroupTitle.value) return
  historyLoading.value = true
  try {
    const data = await getIxBrowserSoraSessionScanHistory(selectedGroupTitle.value, 10)
    historyRuns.value = Array.isArray(data) ? data : []
  } catch (error) {
    if (error?.response?.status !== 404) {
      ElMessage.error(error?.response?.data?.detail || '获取历史失败')
    }
    historyRuns.value = []
  } finally {
    historyLoading.value = false
  }
}

const loadLatest = async () => {
  if (!selectedGroupTitle.value) return
  latestLoading.value = true
  try {
    const data = await getLatestIxBrowserSoraSessionAccounts(selectedGroupTitle.value, true)
    scanData.value = data
    activeRunId.value = data?.run_id || null
  } catch (error) {
    if (error?.response?.status === 404) {
      scanData.value = null
      activeRunId.value = null
      return
    }
    ElMessage.error(error?.response?.data?.detail || '获取最新结果失败')
  } finally {
    latestLoading.value = false
  }
}

const loadGenerateJobs = async () => {
  if (!selectedGroupTitle.value) return
  generateJobsLoading.value = true
  try {
    const data = await listIxBrowserSoraGenerateJobs({
      group_title: selectedGroupTitle.value,
      limit: 20
    })
    generateJobs.value = Array.isArray(data) ? data : []
    const running = generateJobs.value.find((item) => item.status === 'queued' || item.status === 'running')
    if (running) {
      startJobPolling(running.job_id)
    } else {
      stopJobPolling()
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '获取文生任务失败')
  } finally {
    generateJobsLoading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([loadHistory(), loadLatest(), loadGenerateJobs()])
}

const scanNow = async () => {
  if (!selectedGroupTitle.value) {
    ElMessage.warning('请先选择分组')
    return
  }
  scanLoading.value = true
  try {
    const data = await scanIxBrowserSoraSessionAccounts(selectedGroupTitle.value)
    scanData.value = data
    activeRunId.value = data?.run_id || null
    ElMessage.success('扫描完成，结果已入库')
    await loadHistory()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '扫描失败')
  } finally {
    scanLoading.value = false
  }
}

const openRun = async (runId) => {
  runLoading.value = true
  try {
    const data = await getIxBrowserSoraSessionByRun(runId, true)
    scanData.value = data
    activeRunId.value = runId
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '读取历史明细失败')
  } finally {
    runLoading.value = false
  }
}

const selectGroup = async (title) => {
  selectedGroupTitle.value = title
  scanData.value = null
  activeRunId.value = null
  generateJobs.value = []
  stopJobPolling()
  await Promise.all([loadHistory(), loadLatest(), loadGenerateJobs()])
}

const onGroupChange = async () => {
  await selectGroup(selectedGroupTitle.value)
}

const openGenerateDialog = (windowRow) => {
  if (!canGenerate.value) {
    ElMessage.warning('仅 Sora 分组支持文生视频')
    return
  }
  generateForm.value = {
    profile_id: windowRow.profile_id,
    prompt: '',
    duration: '10s',
    aspect_ratio: 'landscape'
  }
  generateDialogVisible.value = true
}

const submitGenerateJob = async () => {
  const prompt = generateForm.value.prompt?.trim()
  if (!prompt) {
    ElMessage.warning('请输入提示词')
    return
  }
  generateSubmitting.value = true
  try {
    const data = await createIxBrowserSoraGenerateJob({
      profile_id: generateForm.value.profile_id,
      prompt,
      duration: generateForm.value.duration,
      aspect_ratio: generateForm.value.aspect_ratio
    })
    const job = data?.job
    generateDialogVisible.value = false
    ElMessage.success('任务已创建，正在监听状态')
    await loadGenerateJobs()
    if (job?.job_id) {
      startJobPolling(job.job_id)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '创建文生任务失败')
  } finally {
    generateSubmitting.value = false
  }
}

const viewSession = (row) => {
  const payload = {
    account: row.account || null,
    session_status: row.session_status || null,
    fallback_applied: row.fallback_applied || false,
    fallback_run_id: row.fallback_run_id || null,
    fallback_scanned_at: row.fallback_scanned_at || null,
    session: row.session ?? row.session_raw ?? null,
    quota: {
      remaining_count: row.quota_remaining_count ?? null,
      total_count: row.quota_total_count ?? null,
      reset_at: row.quota_reset_at ?? null,
      source: row.quota_source ?? null,
      payload: row.quota_payload ?? null,
      error: row.quota_error ?? null
    }
  }
  currentSessionText.value = JSON.stringify(payload, null, 2)
  sessionDialogVisible.value = true
}

onMounted(async () => {
  await loadGroups()
  await Promise.all([loadHistory(), loadLatest(), loadGenerateJobs()])
})

onUnmounted(() => {
  stopJobPolling()
})
</script>

<style scoped>
.ix-page {
  padding: 18px;
  min-height: calc(100vh - 80px);
  background: radial-gradient(circle at top right, #e7f0ff 0%, #f7fafc 44%, #f8fafc 100%);
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 52%, #0b5fa8 100%);
  color: #f8fafc;
  border-radius: 16px;
  padding: 18px 20px;
  margin-bottom: 14px;
}

.hero-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.hero-subtitle {
  margin: 6px 0 0;
  color: #cbd5e1;
  font-size: 13px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.group-select {
  width: 260px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.metric-card {
  background: #ffffff;
  border: 1px solid #dbe7fb;
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
}

.metric-card.success {
  border-color: #bbf7d0;
}

.metric-card.danger {
  border-color: #fecaca;
}

.metric-card.warning {
  border-color: #fde68a;
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  display: block;
  margin-top: 6px;
  font-size: 28px;
  line-height: 1;
  color: #0f172a;
}

.content-grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 12px;
}

.left-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.right-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel {
  border-radius: 12px;
  border: 1px solid #dbe7fb;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #1e293b;
}

.group-item,
.history-item {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.18s;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  background: #fff;
}

.group-item:hover,
.history-item:hover {
  border-color: #60a5fa;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.12);
}

.group-item.active,
.history-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.group-name {
  font-weight: 600;
  color: #0f172a;
}

.group-meta {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}

.history-item {
  display: block;
}

.history-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 13px;
  color: #0f172a;
}

.history-top small {
  color: #64748b;
}

.history-stats {
  display: flex;
  align-items: center;
  gap: 6px;
}

.run-head {
  align-items: flex-start;
}

.run-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.run-meta {
  margin-top: 4px;
  display: flex;
  gap: 14px;
  color: #64748b;
  font-size: 12px;
}

.task-link {
  color: #1d4ed8;
  text-decoration: none;
}

.task-link:hover {
  text-decoration: underline;
}

.scan-table :deep(.el-table__cell),
.jobs-panel :deep(.el-table__cell),
.windows-panel :deep(.el-table__cell) {
  font-size: 12px;
}

.session-preview {
  margin: 0;
  max-height: 520px;
  overflow: auto;
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 8px;
}

@media (max-width: 1360px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .hero-actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
