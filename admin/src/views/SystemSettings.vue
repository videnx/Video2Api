<template>
  <div class="settings-page">
    <el-row :gutter="12">
      <el-col :span="24">
        <el-card class="glass-card" v-loading="loading">
          <template #header>
            <div class="card-title">系统设置</div>
          </template>

          <el-tabs v-model="activeTab" class="settings-tabs">
            <el-tab-pane label="连接" name="ixbrowser">
              <el-form :model="systemForm" label-width="200px">
                <el-form-item label="ixBrowser API Base">
                  <el-input v-model="systemForm.ixbrowser.api_base" />
                </el-form-item>
                <el-form-item label="请求超时（ms）">
                  <el-input-number v-model="systemForm.ixbrowser.request_timeout_ms" :min="1000" :max="120000" />
                </el-form-item>
                <el-form-item label="忙重试次数">
                  <el-input-number v-model="systemForm.ixbrowser.busy_retry_max" :min="0" :max="20" />
                </el-form-item>
                <el-form-item label="忙重试间隔（秒）">
                  <el-input-number v-model="systemForm.ixbrowser.busy_retry_delay_seconds" :min="0.1" :max="30" :step="0.1" />
                </el-form-item>
                <el-form-item label="分组窗口缓存 TTL（秒）">
                  <el-input-number v-model="systemForm.ixbrowser.group_windows_cache_ttl_sec" :min="5" :max="3600" />
                </el-form-item>
                <el-form-item label="实时配额缓存 TTL（秒）">
                  <el-input-number v-model="systemForm.ixbrowser.realtime_quota_cache_ttl_sec" :min="1" :max="600" />
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="任务" name="sora">
              <el-form :model="systemForm" label-width="200px">
                <el-form-item label="最大并发">
                  <el-input-number v-model="systemForm.sora.job_max_concurrency" :min="1" :max="10" />
                </el-form-item>
                <el-form-item label="任务轮询间隔（秒）">
                  <el-input-number v-model="systemForm.sora.generate_poll_interval_sec" :min="3" :max="60" />
                </el-form-item>
                <el-form-item label="任务最大等待（分钟）">
                  <el-input-number v-model="systemForm.sora.generate_max_minutes" :min="1" :max="120" />
                </el-form-item>
                <el-form-item label="Draft 等待超时（分钟）">
                  <el-input-number v-model="systemForm.sora.draft_wait_timeout_minutes" :min="1" :max="120" />
                </el-form-item>
                <el-form-item label="Draft 手动轮询（分钟）">
                  <el-input-number v-model="systemForm.sora.draft_manual_poll_interval_minutes" :min="1" :max="60" />
                </el-form-item>
                <el-form-item label="阻塞资源类型">
                  <el-select
                    v-model="systemForm.sora.blocked_resource_types"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    style="width: 100%"
                  >
                    <el-option label="image" value="image" />
                    <el-option label="media" value="media" />
                    <el-option label="font" value="font" />
                  </el-select>
                </el-form-item>
                <el-form-item label="默认分组">
                  <el-input v-model="systemForm.sora.default_group_title" />
                </el-form-item>
                <el-form-item label="默认时长">
                  <el-select v-model="systemForm.sora.default_duration" style="width: 100%">
                    <el-option label="10s" value="10s" />
                    <el-option label="15s" value="15s" />
                    <el-option label="25s" value="25s" />
                  </el-select>
                </el-form-item>
                <el-form-item label="默认比例">
                  <el-select v-model="systemForm.sora.default_aspect_ratio" style="width: 100%">
                    <el-option label="landscape" value="landscape" />
                    <el-option label="portrait" value="portrait" />
                  </el-select>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="去水印" name="watermark">
              <el-form :model="watermarkForm" label-width="200px">
                <el-form-item label="启用去水印">
                  <div class="field-row">
                    <el-switch v-model="watermarkForm.enabled" />
                    <div class="inline-tip">关闭后将无法完成任务。</div>
                  </div>
                </el-form-item>
                <el-form-item label="解析方式">
                  <el-select v-model="watermarkForm.parse_method" style="width: 100%">
                    <el-option label="自定义解析" value="custom" />
                    <el-option label="第三方解析" value="third_party" />
                  </el-select>
                </el-form-item>
                <template v-if="watermarkForm.parse_method === 'custom'">
                  <el-form-item label="解析服务器地址">
                    <el-input v-model="watermarkForm.custom_parse_url" placeholder="例如：http://127.0.0.1:5001" />
                  </el-form-item>
                  <el-form-item label="访问密钥">
                    <el-input
                      v-model="watermarkForm.custom_parse_token"
                      type="password"
                      show-password
                      placeholder="可选"
                    />
                  </el-form-item>
                  <el-form-item label="解析路径">
                    <el-input v-model="watermarkForm.custom_parse_path" placeholder="/get-sora-link" />
                  </el-form-item>
                </template>
                <el-form-item label="最大重试次数">
                  <el-input-number v-model="watermarkForm.retry_max" :min="0" :max="10" />
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="扫描" name="scan">
              <el-form :model="systemForm" label-width="200px">
                <el-form-item label="历史保留条数">
                  <el-input-number v-model="systemForm.scan.history_limit" :min="1" :max="50" />
                </el-form-item>
                <el-form-item label="默认分组">
                  <el-input v-model="systemForm.scan.default_group_title" />
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="日志" name="logging">
              <el-form :model="systemForm" label-width="200px">
                <el-form-item label="日志等级">
                  <div class="field-row">
                    <el-select v-model="systemForm.logging.log_level" class="flex-1">
                      <el-option label="DEBUG" value="DEBUG" />
                      <el-option label="INFO" value="INFO" />
                      <el-option label="WARN" value="WARN" />
                      <el-option label="ERROR" value="ERROR" />
                    </el-select>
                    <el-tag v-if="isRequiresRestart('logging.log_level')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="日志文件">
                  <div class="field-row">
                    <el-input v-model="systemForm.logging.log_file" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('logging.log_file')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="日志最大大小（Bytes）">
                  <div class="field-row">
                    <el-input-number v-model="systemForm.logging.log_max_bytes" :min="1048576" :max="104857600" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('logging.log_max_bytes')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="日志备份数量">
                  <div class="field-row">
                    <el-input-number v-model="systemForm.logging.log_backup_count" :min="1" :max="100" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('logging.log_backup_count')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="审计日志保留天数">
                  <el-input-number v-model="systemForm.logging.audit_log_retention_days" :min="0" :max="365" />
                </el-form-item>
                <el-form-item label="审计清理间隔（秒）">
                  <el-input-number v-model="systemForm.logging.audit_log_cleanup_interval_sec" :min="60" :max="86400" />
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="安全" name="security">
              <el-form :model="systemForm" label-width="200px">
                <el-form-item label="JWT Secret">
                  <div class="field-row">
                    <el-input
                      v-model="systemForm.auth.secret_key"
                      type="password"
                      show-password
                      placeholder="留空不修改"
                      class="flex-1"
                    />
                    <el-tag v-if="isRequiresRestart('auth.secret_key')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="JWT Algorithm">
                  <div class="field-row">
                    <el-input v-model="systemForm.auth.algorithm" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('auth.algorithm')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="Token 过期（分钟）">
                  <el-input-number v-model="systemForm.auth.access_token_expire_minutes" :min="5" :max="10080" />
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="服务" name="server">
              <el-form :model="systemForm" label-width="200px">
                <el-form-item label="应用名称">
                  <div class="field-row">
                    <el-input v-model="systemForm.server.app_name" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('server.app_name')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="调试模式">
                  <div class="field-row">
                    <el-switch v-model="systemForm.server.debug" />
                    <el-tag v-if="isRequiresRestart('server.debug')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="监听地址">
                  <div class="field-row">
                    <el-input v-model="systemForm.server.host" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('server.host')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="端口">
                  <div class="field-row">
                    <el-input-number v-model="systemForm.server.port" :min="1" :max="65535" class="flex-1" />
                    <el-tag v-if="isRequiresRestart('server.port')" type="warning" size="small">需重启</el-tag>
                  </div>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="定时" name="scheduler">
              <el-form :model="schedulerForm" label-width="140px">
                <el-form-item label="启用定时">
                  <el-switch v-model="schedulerForm.enabled" />
                </el-form-item>
                <el-form-item label="执行时刻">
                  <el-input v-model="schedulerForm.times" placeholder="例如：09:00,13:30,21:10" />
                  <div class="inline-tip">24 小时制，多个时刻用英文逗号分隔。</div>
                </el-form-item>
                <el-form-item label="时区">
                  <el-input v-model="schedulerForm.timezone" />
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="glass-card save-card">
      <div class="save-row">
        <div class="save-left">
          <div class="save-desc">配置修改后立即生效（标记需重启的除外）</div>
          <div class="save-meta" v-if="systemUpdatedAt">最近保存：{{ systemUpdatedAt }}</div>
        </div>
        <div class="save-actions">
          <el-button @click="loadAll">重置</el-button>
          <el-button type="primary" :loading="saving" @click="saveAll">保存设置</el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getScanSchedulerConfig,
  getSystemSettings,
  updateScanSchedulerConfig,
  updateSystemSettings,
  getWatermarkFreeConfig,
  updateWatermarkFreeConfig
} from '../api'

const loading = ref(false)
const saving = ref(false)
const activeTab = ref('ixbrowser')

const defaultSystemForm = {
  ixbrowser: {
    api_base: 'http://127.0.0.1:53200',
    request_timeout_ms: 10000,
    busy_retry_max: 6,
    busy_retry_delay_seconds: 1.2,
    group_windows_cache_ttl_sec: 120,
    realtime_quota_cache_ttl_sec: 30
  },
  sora: {
    job_max_concurrency: 2,
    generate_poll_interval_sec: 6,
    generate_max_minutes: 30,
    draft_wait_timeout_minutes: 20,
    draft_manual_poll_interval_minutes: 5,
    blocked_resource_types: ['image', 'media', 'font'],
    default_group_title: 'Sora',
    default_duration: '10s',
    default_aspect_ratio: 'landscape'
  },
  scan: {
    history_limit: 10,
    default_group_title: 'Sora'
  },
  logging: {
    log_level: 'INFO',
    log_file: 'logs/app.log',
    log_max_bytes: 10485760,
    log_backup_count: 5,
    audit_log_retention_days: 3,
    audit_log_cleanup_interval_sec: 3600
  },
  auth: {
    secret_key: null,
    algorithm: 'HS256',
    access_token_expire_minutes: 10080
  },
  server: {
    app_name: 'Video2Api',
    debug: true,
    host: '0.0.0.0',
    port: 8001
  }
}

const defaultSchedulerForm = {
  enabled: false,
  times: '09:00,13:30,21:00',
  timezone: 'Asia/Shanghai'
}

const defaultWatermarkForm = {
  enabled: true,
  parse_method: 'custom',
  custom_parse_url: '',
  custom_parse_token: '',
  custom_parse_path: '/get-sora-link',
  retry_max: 2
}

const systemForm = ref({ ...defaultSystemForm })
const schedulerForm = ref({ ...defaultSchedulerForm })
const watermarkForm = ref({ ...defaultWatermarkForm })
const systemDefaults = ref({ ...defaultSystemForm })
const schedulerDefaults = ref({ ...defaultSchedulerForm })
const watermarkDefaults = ref({ ...defaultWatermarkForm })
const requiresRestart = ref([])
const systemUpdatedAt = ref('')

const mergeSettings = (base, override) => {
  const result = Array.isArray(base) ? [...base] : { ...base }
  Object.keys(override || {}).forEach((key) => {
    const baseValue = result[key]
    const overrideValue = override[key]
    if (
      baseValue &&
      overrideValue &&
      typeof baseValue === 'object' &&
      !Array.isArray(baseValue) &&
      typeof overrideValue === 'object' &&
      !Array.isArray(overrideValue)
    ) {
      result[key] = mergeSettings(baseValue, overrideValue)
    } else {
      result[key] = overrideValue
    }
  })
  return result
}

const isRequiresRestart = (path) => requiresRestart.value.includes(path)

const loadAll = async () => {
  loading.value = true
  try {
    const [systemEnvelope, schedulerEnvelope, watermarkConfig] = await Promise.all([
      getSystemSettings(),
      getScanSchedulerConfig(),
      getWatermarkFreeConfig()
    ])
    const systemData = systemEnvelope?.data || {}
    const systemDefault = systemEnvelope?.defaults || defaultSystemForm
    systemDefaults.value = mergeSettings(defaultSystemForm, systemDefault)
    systemForm.value = mergeSettings(systemDefaults.value, systemData)
    requiresRestart.value = systemEnvelope?.requires_restart || []
    systemUpdatedAt.value = systemEnvelope?.updated_at || ''

    const schedulerData = schedulerEnvelope?.data || {}
    const schedulerDefault = schedulerEnvelope?.defaults || defaultSchedulerForm
    schedulerDefaults.value = mergeSettings(defaultSchedulerForm, schedulerDefault)
    schedulerForm.value = mergeSettings(schedulerDefaults.value, schedulerData)

    const watermarkData = watermarkConfig || {}
    watermarkDefaults.value = mergeSettings(defaultWatermarkForm, watermarkData)
    watermarkForm.value = mergeSettings(defaultWatermarkForm, watermarkData)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '读取系统设置失败')
  } finally {
    loading.value = false
  }
}

const validateTimes = (value) => {
  const times = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  if (times.length === 0) {
    return false
  }
  const pattern = /^([01]\d|2[0-3]):[0-5]\d$/
  return times.every((item) => pattern.test(item))
}

const normalizePayload = (payload) => {
  const data = JSON.parse(JSON.stringify(payload))
  if (data?.auth) {
    if (data.auth.secret_key !== null && typeof data.auth.secret_key === 'string') {
      if (!data.auth.secret_key.trim()) {
        data.auth.secret_key = null
      }
    }
  }
  return data
}

const saveAll = async () => {
  if (!validateTimes(schedulerForm.value.times)) {
    ElMessage.warning('执行时刻格式不正确，请输入 HH:mm 并用逗号分隔')
    activeTab.value = 'scheduler'
    return
  }
  if (watermarkForm.value.enabled && watermarkForm.value.parse_method === 'custom') {
    const url = String(watermarkForm.value.custom_parse_url || '').trim()
    if (!url) {
      ElMessage.warning('请填写去水印解析服务器地址')
      activeTab.value = 'watermark'
      return
    }
  }
  saving.value = true
  try {
    const payload = normalizePayload(systemForm.value)
    const watermarkPayload = {
      ...watermarkForm.value,
      custom_parse_path: (watermarkForm.value.custom_parse_path || '').trim() || '/get-sora-link'
    }
    const [systemEnvelope, schedulerEnvelope, watermarkConfig] = await Promise.all([
      updateSystemSettings(payload),
      updateScanSchedulerConfig(schedulerForm.value),
      updateWatermarkFreeConfig(watermarkPayload)
    ])
    requiresRestart.value = systemEnvelope?.requires_restart || []
    systemUpdatedAt.value = systemEnvelope?.updated_at || ''
    const systemData = systemEnvelope?.data || {}
    const systemDefault = systemEnvelope?.defaults || defaultSystemForm
    systemDefaults.value = mergeSettings(defaultSystemForm, systemDefault)
    systemForm.value = mergeSettings(systemDefaults.value, systemData)

    const schedulerData = schedulerEnvelope?.data || {}
    const schedulerDefault = schedulerEnvelope?.defaults || defaultSchedulerForm
    schedulerDefaults.value = mergeSettings(defaultSchedulerForm, schedulerDefault)
    schedulerForm.value = mergeSettings(schedulerDefaults.value, schedulerData)

    if (watermarkConfig) {
      watermarkDefaults.value = mergeSettings(defaultWatermarkForm, watermarkConfig)
      watermarkForm.value = mergeSettings(defaultWatermarkForm, watermarkConfig)
    }

    ElMessage.success('系统设置已保存并生效')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--page-gap);
  background: transparent;
}

.card-title {
  font-weight: 700;
  color: var(--ink);
}

.settings-tabs :deep(.el-tabs__content) {
  padding-top: 4px;
}

.inline-tip {
  margin-top: 6px;
  font-size: 12px;
  color: #475569;
}

.save-card {
  margin-top: 0;
}

.save-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.save-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.save-desc {
  color: #0f172a;
  font-weight: 600;
}

.save-meta {
  color: #64748b;
  font-size: 12px;
}

.save-actions {
  display: flex;
  gap: 10px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.flex-1 {
  flex: 1;
}
</style>
