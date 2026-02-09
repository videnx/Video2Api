<template>
  <div class="nurture-page">
    <section class="command-bar" v-loading="pageLoading">
      <div class="command-left">
        <div class="command-title">养号任务</div>
        <div class="filters">
          <el-select v-model="selectedGroupTitle" class="w-180" @change="onGroupChange">
            <el-option
              v-for="group in groups"
              :key="group.id"
              :label="`${group.title} (ID:${group.id})`"
              :value="group.title"
            />
          </el-select>

          <el-select v-model="batchStatus" class="w-140" @change="loadBatches">
            <el-option label="全部状态" value="all" />
            <el-option label="排队中" value="queued" />
            <el-option label="运行中" value="running" />
            <el-option label="成功" value="completed" />
            <el-option label="失败" value="failed" />
            <el-option label="已取消" value="canceled" />
          </el-select>

          <el-tag size="large" effect="light" type="info">一次刷 {{ createForm.scroll_count }} 条</el-tag>
          <el-tag size="large" effect="light" :type="hasActiveBatches ? 'warning' : 'success'">
            轮询 {{ hasActiveBatches ? '活跃' : '空闲' }} · {{ pollDelayMs }}ms
          </el-tag>
        </div>
      </div>
      <div class="command-right">
        <el-button @click="refreshAll">刷新</el-button>
        <el-button
          type="warning"
          :loading="creating"
          :disabled="!selectedTargets.length"
          @click="createBatch"
        >
          创建并开始
        </el-button>
      </div>
    </section>

    <section class="workflow-steps">
      <article class="step-pill" :class="{ active: selectedTargets.length > 0 }">
        <div class="step-index">1</div>
        <div class="step-body">
          <div class="step-title">选择账号</div>
          <div class="step-meta">{{ selectedTargets.length }} 个窗口已选</div>
        </div>
      </article>
      <article class="step-pill" :class="{ active: createForm.scroll_count > 0 }">
        <div class="step-index">2</div>
        <div class="step-body">
          <div class="step-title">配置策略</div>
          <div class="step-meta">点赞 {{ createForm.like_probability }} · 关注 {{ createForm.follow_probability }}</div>
        </div>
      </article>
      <article class="step-pill" :class="{ active: batches.length > 0 }">
        <div class="step-index">3</div>
        <div class="step-body">
          <div class="step-title">运行监控</div>
          <div class="step-meta">活跃 {{ monitorStats.active }} · 失败 {{ monitorStats.failed }}</div>
        </div>
      </article>
    </section>

    <section class="step-grid">
      <el-card class="table-card step-card" v-loading="groupsLoading || windowsLoading">
        <template #header>
          <div class="table-head stack">
            <span>步骤 1：选择账号</span>
            <span class="table-hint">从养号/Sora 分组勾选窗口，可跨组混选</span>
          </div>
        </template>

        <div v-if="visibleSelectableGroups.length" class="group-select-panel">
          <el-collapse v-model="activeGroupNames">
            <el-collapse-item
              v-for="group in visibleSelectableGroups"
              :key="group.title"
              :name="group.title"
            >
              <template #title>
                <div class="pick-group-head">
                  <el-checkbox
                    :model-value="isGroupChecked(group.title)"
                    :indeterminate="isGroupIndeterminate(group.title)"
                    @change="(checked) => toggleGroupTargets(group.title, checked)"
                    @click.stop
                  />
                  <span class="pick-group-title">{{ group.title }}</span>
                  <span class="pick-group-count">{{ group.rows.length }} 个窗口</span>
                </div>
              </template>

              <div class="group-window-list">
                <div
                  v-for="row in group.rows"
                  :key="targetKey(group.title, row.profile_id)"
                  class="group-window-row"
                >
                  <el-checkbox
                    :model-value="isTargetChecked(group.title, row.profile_id)"
                    @change="(checked) => toggleSingleTarget(group.title, row, checked)"
                  />
                  <div class="window-cell">
                    <div class="window-name">{{ row.window_name || '-' }}</div>
                    <div class="window-meta">ID {{ row.profile_id }}</div>
                    <div v-if="row.proxy_ip && row.proxy_port" class="window-proxy">{{ formatProxy(row) }}</div>
                  </div>
                  <div class="account-cell">
                    <span class="account-text">{{ row.account || '-' }}</span>
                    <span v-if="row.account_plan === 'plus'" class="plan-badge">Plus</span>
                  </div>
                  <div class="window-extra">
                    可用 {{ row.quota_remaining_count ?? '-' }} · {{ formatTime(row.scanned_at) }}
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-empty v-else description="暂无可选账号（养号/Sora 分组为空）" :image-size="90">
          <el-button @click="loadGroups" :loading="groupsLoading">重新加载</el-button>
        </el-empty>
      </el-card>

      <el-card class="table-card step-card">
        <template #header>
          <div class="table-head stack">
            <span>步骤 2：配置策略并创建</span>
            <span class="table-hint">失败账号支持批次内重跑（仅 failed）</span>
          </div>
        </template>

        <div class="create-panel">
          <el-form :model="createForm" label-width="120px" class="create-form">
            <el-form-item label="任务组名称">
              <el-input v-model="createForm.name" placeholder="可留空，系统自动生成" maxlength="60" />
            </el-form-item>

            <el-form-item label="刷条数">
              <el-input-number v-model="createForm.scroll_count" :min="1" :max="50" />
            </el-form-item>

            <el-form-item label="高级参数">
              <div class="advanced-grid">
                <div class="advanced-item">
                  <div class="advanced-label">点赞概率</div>
                  <el-input-number v-model="createForm.like_probability" :min="0" :max="1" :step="0.01" />
                </div>
                <div class="advanced-item">
                  <div class="advanced-label">关注概率</div>
                  <el-input-number v-model="createForm.follow_probability" :min="0" :max="1" :step="0.01" />
                </div>
                <div class="advanced-item">
                  <div class="advanced-label">单号最多关注</div>
                  <el-input-number v-model="createForm.max_follows_per_profile" :min="0" :max="1000" />
                </div>
                <div class="advanced-item">
                  <div class="advanced-label">单号最多点赞</div>
                  <el-input-number v-model="createForm.max_likes_per_profile" :min="0" :max="1000" />
                </div>
              </div>
            </el-form-item>
          </el-form>

          <aside class="selection-summary">
            <div class="selection-tip">已选 <strong>{{ selectedTargets.length }}</strong> 个窗口</div>
            <div class="selection-sub">去重窗口 ID：{{ selectedProfileIds.length }}</div>
            <el-button
              type="warning"
              :loading="creating"
              :disabled="!selectedTargets.length"
              @click="createBatch"
            >
              创建并开始
            </el-button>
          </aside>
        </div>
      </el-card>
    </section>

    <section class="monitor-grid">
      <el-card class="table-card" v-loading="batchesLoading">
        <template #header>
          <div class="table-head stack">
            <div class="monitor-title-row">
              <span>任务组列表</span>
              <span class="table-hint">批次点击行可查看明细；运行中自动高频轮询</span>
            </div>
            <div class="monitor-stats-row">
              <span class="summary-item">总数 {{ monitorStats.total }}</span>
              <span class="summary-item running">活跃 {{ monitorStats.active }}</span>
              <span class="summary-item success">成功 {{ monitorStats.completed }}</span>
              <span class="summary-item failed">失败 {{ monitorStats.failed }}</span>
              <span class="summary-item muted">取消 {{ monitorStats.canceled }}</span>
            </div>
          </div>
        </template>

        <el-table
          :data="batches"
          class="card-table"
          empty-text="暂无任务组"
          highlight-current-row
          @row-click="selectBatch"
        >
          <el-table-column label="Batch" width="92">
            <template #default="{ row }">#{{ row.batch_id }}</template>
          </el-table-column>
          <el-table-column label="名称" min-width="220">
            <template #default="{ row }">
              <div class="batch-name">{{ row.name || '-' }}</div>
              <div class="batch-meta">窗口数 {{ row.total_jobs }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="148" align="center">
            <template #default="{ row }">
              <div class="batch-status-cell">
                <el-tag size="small" :type="batchStatusTag(row.status)">{{ batchStatusText(row.status) }}</el-tag>
                <el-tag v-if="isBatchPossiblyStuck(row)" size="small" type="danger" effect="plain">疑似卡住</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="统计" width="170" align="center">
            <template #default="{ row }">
              <span class="stat-ok">{{ row.success_count }}</span>
              <span class="stat-split">/</span>
              <span class="stat-fail">{{ row.failed_count }}</span>
              <span class="stat-split">/</span>
              <span class="stat-cancel">{{ row.canceled_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="赞/关" width="120" align="center">
            <template #default="{ row }">
              <span>{{ row.like_total }}/{{ row.follow_total }}</span>
            </template>
          </el-table-column>
          <el-table-column label="错误摘要" min-width="220">
            <template #default="{ row }">
              <span class="error-text" :class="{ danger: row.error }">{{ shorten(row.error, 70) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="180" align="center">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="220" align="center">
            <template #default="{ row }">
              <div class="batch-actions">
                <el-button
                  size="small"
                  @click.stop="selectBatch(row)"
                >
                  查看
                </el-button>
                <el-button
                  v-if="row.status === 'queued' || row.status === 'running'"
                  size="small"
                  type="warning"
                  @click.stop="cancelBatch(row)"
                >
                  取消
                </el-button>
                <el-button
                  v-if="canRetryBatch(row)"
                  size="small"
                  type="primary"
                  plain
                  @click.stop="retryBatch(row)"
                >
                  重试失败
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="selectedBatch" class="table-card" v-loading="jobsLoading">
        <template #header>
          <div class="table-head stack">
            <div class="monitor-title-row">
              <span>任务明细（Batch #{{ selectedBatch.batch_id }}）</span>
              <span class="table-hint">{{ selectedBatch.name || '-' }}</span>
            </div>
            <div class="monitor-stats-row">
              <span class="summary-item">总任务 {{ jobs.length }}</span>
              <span class="summary-item running">运行 {{ selectedJobsStats.running }}</span>
              <span class="summary-item failed">失败 {{ selectedJobsStats.failed }}</span>
              <span class="summary-item muted">疑似卡住 {{ stuckJobCount }}</span>
            </div>
          </div>
        </template>

        <el-alert
          v-if="stuckJobCount > 0"
          class="stuck-alert"
          type="warning"
          show-icon
          :closable="false"
          title="检测到疑似卡住任务（基于 updated_at 超过 3 分钟）"
        />

        <el-table :data="jobs" class="card-table" empty-text="暂无任务">
          <el-table-column label="窗口" min-width="240">
            <template #default="{ row }">
              <div class="window-cell">
                <div class="window-name">{{ row.window_name || '-' }}</div>
                <div class="window-meta">ID {{ row.profile_id }}</div>
                <div v-if="row.proxy_ip && row.proxy_port" class="window-proxy">{{ formatProxy(row) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="156" align="center">
            <template #default="{ row }">
              <div class="job-status-cell">
                <el-tag size="small" :type="jobStatusTag(row.status)">{{ row.status }}</el-tag>
                <el-tag v-if="isJobPossiblyStuck(row)" size="small" type="danger" effect="plain">疑似卡住</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="110" align="center">
            <template #default="{ row }">{{ row.phase }}</template>
          </el-table-column>
          <el-table-column label="进度" width="180">
            <template #default="{ row }">
              <div class="progress-cell">
                <el-progress
                  v-if="row.scroll_target > 0"
                  :percentage="progressPct(row)"
                  :stroke-width="8"
                  :text-inside="true"
                  :status="row.status === 'failed' ? 'exception' : undefined"
                />
                <div class="progress-text">{{ row.scroll_done }}/{{ row.scroll_target }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="赞/关" width="120" align="center">
            <template #default="{ row }">{{ row.like_count }}/{{ row.follow_count }}</template>
          </el-table-column>
          <el-table-column label="错误" min-width="250">
            <template #default="{ row }">
              <span class="error-text" :class="{ danger: row.error }">{{ shorten(row.error, 90) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="180" align="center">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createNurtureBatch,
  listNurtureBatches,
  listNurtureJobs,
  cancelNurtureBatch,
  retryNurtureBatch,
  getIxBrowserGroupWindows,
  getLatestIxBrowserSoraSessionAccounts
} from '../api'

const TARGET_GROUP_TITLES = ['养号', 'Sora']
const ACTIVE_BATCH_STATUSES = new Set(['queued', 'running'])
const STUCK_THRESHOLD_MS = 3 * 60 * 1000

const groupsLoading = ref(false)
const windowsLoading = ref(false)
const batchesLoading = ref(false)
const jobsLoading = ref(false)
const creating = ref(false)
const pageLoading = computed(() => groupsLoading.value || windowsLoading.value || batchesLoading.value || jobsLoading.value)

const groups = ref([])
const selectedGroupTitle = ref('Sora')
const batchStatus = ref('all')

const latestScanByGroup = ref({})
const activeGroupNames = ref([])
const selectedTargets = ref([])

const createForm = ref({
  name: '',
  scroll_count: 10,
  like_probability: 0.25,
  follow_probability: 0.15,
  max_follows_per_profile: 100,
  max_likes_per_profile: 100
})

const batches = ref([])
const selectedBatch = ref(null)
const jobs = ref([])
const pollDelayMs = ref(0)

let pollTimer = null
let pollTickRunning = false
let batchesRequesting = false
let jobsRequesting = false

const targetKey = (groupTitle, profileId) => `${String(groupTitle || '').trim()}::${Number(profileId || 0)}`

const visibleSelectableGroups = computed(() => {
  const result = []
  for (const title of TARGET_GROUP_TITLES) {
    const group = groups.value.find((item) => String(item?.title || '').trim() === title)
    const windows = Array.isArray(group?.windows) ? group.windows : []
    if (!windows.length) continue
    const scanRows = latestScanByGroup.value?.[title]?.results || []
    const scanMap = {}
    for (const row of scanRows) {
      const pid = Number(row?.profile_id)
      if (!Number.isFinite(pid) || pid <= 0) continue
      scanMap[pid] = row
    }
    const rows = windows.map((win) => {
      const pid = Number(win.profile_id)
      const scan = scanMap[pid] || null
      return {
        group_title: title,
        profile_id: pid,
        window_name: win.name,
        account: scan?.account || '',
        account_plan: scan?.account_plan || '',
        quota_remaining_count: scan?.quota_remaining_count,
        scanned_at: scan?.scanned_at || '',
        proxy_type: win.proxy_type,
        proxy_ip: win.proxy_ip,
        proxy_port: win.proxy_port,
        proxy_local_id: win.proxy_local_id
      }
    })
    rows.sort((a, b) => Number(b.profile_id) - Number(a.profile_id))
    if (!rows.length) continue
    result.push({ title, rows })
  }
  return result
})

const selectedTargetKeySet = computed(() => {
  const set = new Set()
  for (const item of selectedTargets.value) {
    set.add(targetKey(item.group_title, item.profile_id))
  }
  return set
})

const selectedProfileIds = computed(() => {
  const out = []
  const seen = new Set()
  for (const item of selectedTargets.value) {
    const pid = Number(item.profile_id)
    if (!Number.isFinite(pid) || pid <= 0) continue
    if (seen.has(pid)) continue
    seen.add(pid)
    out.push(pid)
  }
  return out
})

const monitorStats = computed(() => {
  const rows = Array.isArray(batches.value) ? batches.value : []
  const stats = {
    total: rows.length,
    active: 0,
    queued: 0,
    running: 0,
    completed: 0,
    failed: 0,
    canceled: 0
  }
  for (const row of rows) {
    const status = String(row?.status || '').trim().toLowerCase()
    if (status === 'queued') stats.queued += 1
    if (status === 'running') stats.running += 1
    if (status === 'completed') stats.completed += 1
    if (status === 'failed') stats.failed += 1
    if (status === 'canceled') stats.canceled += 1
  }
  stats.active = stats.queued + stats.running
  return stats
})

const hasActiveBatches = computed(() => monitorStats.value.active > 0)

const selectedJobsStats = computed(() => {
  const rows = Array.isArray(jobs.value) ? jobs.value : []
  const stats = {
    running: 0,
    failed: 0
  }
  for (const row of rows) {
    const status = String(row?.status || '').trim().toLowerCase()
    if (status === 'running') stats.running += 1
    if (status === 'failed') stats.failed += 1
  }
  return stats
})

const isJobPossiblyStuck = (row) => {
  if (String(row?.status || '').trim().toLowerCase() !== 'running') return false
  const ts = Date.parse(String(row?.updated_at || ''))
  if (!Number.isFinite(ts) || ts <= 0) return false
  return (Date.now() - ts) > STUCK_THRESHOLD_MS
}

const isBatchPossiblyStuck = (row) => {
  const status = String(row?.status || '').trim().toLowerCase()
  if (!ACTIVE_BATCH_STATUSES.has(status)) return false
  const ts = Date.parse(String(row?.updated_at || ''))
  if (!Number.isFinite(ts) || ts <= 0) return false
  return (Date.now() - ts) > STUCK_THRESHOLD_MS
}

const stuckJobCount = computed(() => jobs.value.filter((row) => isJobPossiblyStuck(row)).length)

const getRowsByGroup = (groupTitle) => {
  const row = visibleSelectableGroups.value.find((item) => item.title === groupTitle)
  return Array.isArray(row?.rows) ? row.rows : []
}

const isTargetChecked = (groupTitle, profileId) => selectedTargetKeySet.value.has(targetKey(groupTitle, profileId))

const isGroupChecked = (groupTitle) => {
  const rows = getRowsByGroup(groupTitle)
  if (!rows.length) return false
  return rows.every((row) => isTargetChecked(groupTitle, row.profile_id))
}

const isGroupIndeterminate = (groupTitle) => {
  const rows = getRowsByGroup(groupTitle)
  if (!rows.length) return false
  const checkedCount = rows.filter((row) => isTargetChecked(groupTitle, row.profile_id)).length
  return checkedCount > 0 && checkedCount < rows.length
}

const pruneSelectedTargets = () => {
  const allowedKeys = new Set()
  for (const group of visibleSelectableGroups.value) {
    for (const row of group.rows) {
      allowedKeys.add(targetKey(group.title, row.profile_id))
    }
  }
  selectedTargets.value = selectedTargets.value.filter((item) => allowedKeys.has(targetKey(item.group_title, item.profile_id)))
}

const syncActiveGroupNames = () => {
  const visibleNames = new Set(visibleSelectableGroups.value.map((item) => item.title))
  activeGroupNames.value = activeGroupNames.value.filter((name) => visibleNames.has(name))
  if (!activeGroupNames.value.length) {
    activeGroupNames.value = Array.from(visibleNames)
  }
}

const toggleSingleTarget = (groupTitle, row, checked) => {
  const key = targetKey(groupTitle, row?.profile_id)
  const targets = selectedTargets.value.slice()
  const next = []
  let has = false
  for (const item of targets) {
    if (targetKey(item.group_title, item.profile_id) === key) {
      has = true
      if (!checked) continue
    }
    next.push(item)
  }
  if (checked && !has) {
    next.push({
      group_title: String(groupTitle || '').trim(),
      profile_id: Number(row?.profile_id || 0)
    })
  }
  selectedTargets.value = next
}

const toggleGroupTargets = (groupTitle, checked) => {
  const rows = getRowsByGroup(groupTitle)
  if (!rows.length) return
  if (checked) {
    const next = selectedTargets.value.slice()
    const existing = new Set(next.map((item) => targetKey(item.group_title, item.profile_id)))
    for (const row of rows) {
      const key = targetKey(groupTitle, row.profile_id)
      if (existing.has(key)) continue
      existing.add(key)
      next.push({ group_title: groupTitle, profile_id: Number(row.profile_id) })
    }
    selectedTargets.value = next
    return
  }
  const removeKeys = new Set(rows.map((row) => targetKey(groupTitle, row.profile_id)))
  selectedTargets.value = selectedTargets.value.filter((item) => !removeKeys.has(targetKey(item.group_title, item.profile_id)))
}

const loadGroups = async () => {
  groupsLoading.value = true
  try {
    const data = await getIxBrowserGroupWindows()
    groups.value = Array.isArray(data) ? data : []
    const sora = groups.value.find((g) => g.title === 'Sora')
    if (sora) {
      selectedGroupTitle.value = 'Sora'
    } else if (groups.value.length > 0 && !groups.value.some((g) => g.title === selectedGroupTitle.value)) {
      selectedGroupTitle.value = groups.value[0].title
    } else if (groups.value.length <= 0) {
      selectedGroupTitle.value = 'Sora'
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '获取分组失败')
  } finally {
    groupsLoading.value = false
    pruneSelectedTargets()
    syncActiveGroupNames()
  }
}

const loadLatestScan = async () => {
  windowsLoading.value = true
  try {
    const targetGroups = TARGET_GROUP_TITLES.filter((title) => groups.value.some((item) => String(item?.title || '').trim() === title))
    const next = {}
    await Promise.all(targetGroups.map(async (title) => {
      try {
        const data = await getLatestIxBrowserSoraSessionAccounts(title, true)
        next[title] = data || null
      } catch (error) {
        if (error?.response?.status !== 404) {
          next[title] = null
          return
        }
        next[title] = null
      }
    }))
    latestScanByGroup.value = next
  } finally {
    windowsLoading.value = false
    pruneSelectedTargets()
    syncActiveGroupNames()
  }
}

const clearSelection = () => {
  selectedTargets.value = []
}

const loadBatches = async ({ silent = false, force = false } = {}) => {
  if (batchesRequesting && !force) return
  batchesRequesting = true
  if (!silent) batchesLoading.value = true
  try {
    const params = {
      group_title: selectedGroupTitle.value,
      limit: 50
    }
    if (batchStatus.value && batchStatus.value !== 'all') params.status = batchStatus.value
    const data = await listNurtureBatches(params)
    batches.value = Array.isArray(data) ? data : []

    if (selectedBatch.value?.batch_id) {
      const refreshed = batches.value.find((item) => item.batch_id === selectedBatch.value.batch_id)
      if (refreshed) {
        selectedBatch.value = refreshed
      } else {
        selectedBatch.value = null
        jobs.value = []
      }
    }
  } catch (error) {
    if (!silent) {
      ElMessage.error(error?.response?.data?.detail || '读取任务组失败')
    }
  } finally {
    batchesRequesting = false
    if (!silent) batchesLoading.value = false
  }
}

const loadJobs = async ({ silent = false, force = false } = {}) => {
  if (!selectedBatch.value?.batch_id) return
  if (jobsRequesting && !force) return
  jobsRequesting = true
  if (!silent) jobsLoading.value = true
  try {
    const data = await listNurtureJobs(selectedBatch.value.batch_id, { limit: 500 })
    jobs.value = Array.isArray(data) ? data : []
  } catch (error) {
    if (!silent) {
      ElMessage.error(error?.response?.data?.detail || '读取任务明细失败')
    }
  } finally {
    jobsRequesting = false
    if (!silent) jobsLoading.value = false
  }
}

const selectBatch = async (row) => {
  selectedBatch.value = row
  await loadJobs({ force: true })
}

const refreshAll = async () => {
  await loadGroups()
  await Promise.all([loadLatestScan(), loadBatches({ force: true })])
  if (selectedBatch.value?.batch_id) {
    await loadJobs({ force: true })
  }
}

const onGroupChange = async () => {
  selectedBatch.value = null
  jobs.value = []
  await loadBatches({ force: true })
}

const createBatch = async () => {
  if (!selectedTargets.value.length) return
  creating.value = true
  try {
    const targets = selectedTargets.value
      .map((item) => ({
        group_title: String(item.group_title || '').trim(),
        profile_id: Number(item.profile_id || 0)
      }))
      .filter((item) => item.group_title && Number.isFinite(item.profile_id) && item.profile_id > 0)
    const hasNurtureGroup = targets.some((item) => item.group_title === '养号')
    const batchGroupTitle = hasNurtureGroup ? '养号' : 'Sora'
    const payload = {
      name: createForm.value.name || null,
      group_title: batchGroupTitle,
      profile_ids: selectedProfileIds.value,
      targets,
      scroll_count: Number(createForm.value.scroll_count),
      like_probability: Number(createForm.value.like_probability),
      follow_probability: Number(createForm.value.follow_probability),
      max_follows_per_profile: Number(createForm.value.max_follows_per_profile),
      max_likes_per_profile: Number(createForm.value.max_likes_per_profile)
    }
    const batch = await createNurtureBatch(payload)
    ElMessage.success(`已创建任务组 #${batch?.batch_id}`)
    clearSelection()
    createForm.value.name = ''
    if (selectedGroupTitle.value !== batchGroupTitle) {
      selectedGroupTitle.value = batchGroupTitle
    }
    await loadBatches({ force: true })
    if (batch?.batch_id) {
      const found = batches.value.find((b) => b.batch_id === batch.batch_id) || batch
      await selectBatch(found)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '创建任务组失败')
  } finally {
    creating.value = false
  }
}

const cancelBatch = async (row) => {
  if (!row?.batch_id) return
  try {
    await ElMessageBox.confirm(`确认取消任务组 #${row.batch_id}？`, '取消确认', {
      confirmButtonText: '取消任务组',
      cancelButtonText: '返回',
      type: 'warning'
    })
  } catch {
    return
  }

  try {
    await cancelNurtureBatch(row.batch_id)
    ElMessage.success('已提交取消')
    await refreshAll()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '取消失败')
  }
}

const canRetryBatch = (row) => {
  if (!row?.batch_id) return false
  const status = String(row?.status || '').trim().toLowerCase()
  if (ACTIVE_BATCH_STATUSES.has(status)) return false
  return Number(row?.failed_count || 0) > 0
}

const retryBatch = async (row) => {
  if (!canRetryBatch(row)) return
  try {
    await ElMessageBox.confirm(`仅重跑失败任务，确认重试 Batch #${row.batch_id}？`, '重试确认', {
      confirmButtonText: '开始重试',
      cancelButtonText: '返回',
      type: 'warning'
    })
  } catch {
    return
  }

  try {
    await retryNurtureBatch(row.batch_id)
    ElMessage.success(`Batch #${row.batch_id} 已重置失败任务并重新排队`)
    await loadBatches({ force: true })
    const next = batches.value.find((item) => item.batch_id === row.batch_id)
    if (next) {
      selectedBatch.value = next
      await loadJobs({ force: true })
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '重试失败')
  }
}

const batchStatusTag = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

const batchStatusText = (status) => {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'completed') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'canceled') return '已取消'
  return status || '-'
}

const jobStatusTag = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  if (status === 'skipped') return 'info'
  return 'info'
}

const progressPct = (row) => {
  const done = Number(row?.scroll_done || 0)
  const total = Number(row?.scroll_target || 0)
  if (!total) return 0
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)))
}

const shorten = (text, maxLen) => {
  const raw = (text || '').toString()
  if (!raw) return '-'
  if (raw.length <= maxLen) return raw
  return `${raw.slice(0, maxLen)}...`
}

const formatProxy = (row) => {
  const ip = String(row?.proxy_ip || '').trim()
  const port = String(row?.proxy_port || '').trim()
  if (!ip || !port) return '-'
  const ptype = String(row?.proxy_type || 'http').trim().toLowerCase() || 'http'
  const localId = Number(row?.proxy_local_id || 0)
  const suffix = localId > 0 ? `#${localId}` : ''
  return `${ptype}://${ip}:${port}${suffix ? ` (${suffix})` : ''}`
}

const formatTime = (value) => {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

const getPollDelay = () => {
  if (document.hidden) {
    return hasActiveBatches.value ? 6000 : 12000
  }
  return hasActiveBatches.value ? 1800 : 5000
}

const pollOnce = async () => {
  if (pollTickRunning) return
  pollTickRunning = true
  try {
    await loadBatches({ silent: true })
    if (selectedBatch.value?.batch_id) {
      await loadJobs({ silent: true })
    }
  } finally {
    pollTickRunning = false
  }
}

const schedulePolling = (delayMs = getPollDelay()) => {
  const next = Math.max(1200, Number(delayMs || getPollDelay()))
  stopPolling()
  pollDelayMs.value = next
  pollTimer = window.setTimeout(async () => {
    await pollOnce()
    schedulePolling(getPollDelay())
  }, next)
}

const startPolling = () => {
  schedulePolling(1500)
}

const stopPolling = () => {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

const onVisibilityChange = () => {
  if (!pollTimer) return
  schedulePolling(getPollDelay())
}

onMounted(async () => {
  await loadGroups()
  await Promise.all([loadLatestScan(), loadBatches({ force: true })])
  startPolling()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.nurture-page {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--page-gap);
}

.workflow-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.step-pill {
  display: flex;
  gap: 10px;
  align-items: center;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.86);
  padding: 10px 12px;
}

.step-pill.active {
  border-color: rgba(14, 165, 164, 0.42);
  background: rgba(236, 253, 250, 0.8);
}

.step-index {
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: var(--ink);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 12px;
}

.step-pill.active .step-index {
  background: rgba(14, 165, 164, 0.2);
  color: #0f766e;
}

.step-body {
  min-width: 0;
}

.step-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink);
}

.step-meta {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.step-grid {
  display: grid;
  grid-template-columns: minmax(520px, 1.4fr) minmax(360px, 1fr);
  gap: var(--page-gap);
  align-items: start;
}

.step-card {
  min-height: 380px;
}

.create-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
}

.create-form {
  flex: 1;
  min-width: 0;
}

.selection-summary {
  width: 220px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.88);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.selection-tip {
  font-size: 13px;
  color: var(--ink);
}

.selection-sub {
  font-size: 12px;
  color: var(--muted);
}

.group-select-panel {
  padding: 10px 16px 14px;
}

.pick-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.pick-group-title {
  font-weight: 700;
  color: var(--ink);
}

.pick-group-count {
  font-size: 12px;
  color: var(--muted);
}

.group-window-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0 4px;
}

.group-window-row {
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) minmax(140px, 180px) minmax(180px, 1fr);
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.26);
  background: rgba(255, 255, 255, 0.96);
}

.window-extra {
  font-size: 12px;
  color: var(--muted);
  text-align: right;
}

.advanced-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(140px, 1fr));
  gap: 10px 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px dashed rgba(148, 163, 184, 0.35);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
}

.advanced-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.advanced-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

.monitor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--page-gap);
}

.monitor-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 10px;
}

.monitor-stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.summary-item {
  font-size: 12px;
  color: var(--muted);
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
}

.summary-item.running {
  color: #b45309;
  background: rgba(251, 191, 36, 0.16);
}

.summary-item.success {
  color: #15803d;
  background: rgba(34, 197, 94, 0.15);
}

.summary-item.failed {
  color: #b91c1c;
  background: rgba(248, 113, 113, 0.16);
}

.summary-item.muted {
  color: #475569;
  background: rgba(148, 163, 184, 0.15);
}

.window-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.window-name {
  font-weight: 700;
  color: var(--ink);
}

.window-meta {
  font-size: 12px;
  color: var(--muted);
}

.window-proxy {
  font-size: 11px;
  color: rgba(15, 23, 42, 0.7);
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-variant-numeric: tabular-nums;
}

.account-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.account-text {
  font-weight: 600;
  color: #1f2937;
}

.plan-badge {
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(14, 165, 164, 0.14);
  border: 1px solid rgba(14, 165, 164, 0.22);
  color: var(--accent-strong);
  font-weight: 800;
  font-size: 11px;
}

.batch-name {
  font-weight: 700;
  color: var(--ink);
}

.batch-meta {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.batch-status-cell,
.job-status-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.batch-actions {
  display: flex;
  gap: 6px;
  justify-content: center;
  flex-wrap: wrap;
}

.stat-ok {
  color: #16a34a;
  font-weight: 800;
}

.stat-fail {
  color: #dc2626;
  font-weight: 800;
}

.stat-cancel {
  color: #64748b;
  font-weight: 800;
}

.stat-split {
  color: rgba(15, 23, 42, 0.35);
  margin: 0 4px;
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-text {
  font-size: 12px;
  color: var(--muted);
  text-align: right;
}

.error-text {
  color: rgba(15, 23, 42, 0.65);
}

.error-text.danger {
  color: #b91c1c;
  font-weight: 600;
}

.stuck-alert {
  margin: 0 16px 12px;
}

.w-140 {
  width: 140px;
}

.w-180 {
  width: 180px;
}

@media (max-width: 1280px) {
  .step-grid {
    grid-template-columns: 1fr;
  }

  .step-card {
    min-height: auto;
  }
}

@media (max-width: 1080px) {
  .workflow-steps {
    grid-template-columns: 1fr;
  }

  .group-window-row {
    grid-template-columns: auto 1fr;
  }

  .window-extra,
  .account-cell {
    grid-column: 2;
    text-align: left;
  }

  .create-panel {
    flex-direction: column;
  }

  .selection-summary {
    width: 100%;
  }
}
</style>
