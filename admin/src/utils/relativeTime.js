const SECOND_MS = 1000
const MINUTE_MS = 60 * SECOND_MS
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

export const formatRelativeTimeZh = (value, nowMs = Date.now()) => {
  if (!value) return '-'

  const targetMs = value instanceof Date ? value.getTime() : new Date(value).getTime()
  if (!Number.isFinite(targetMs)) return '-'

  const deltaMs = nowMs - targetMs
  if (!Number.isFinite(deltaMs) || deltaMs <= 0) return '刚刚'

  if (deltaMs < MINUTE_MS) return '刚刚'

  const minutes = Math.floor(deltaMs / MINUTE_MS)
  if (minutes < 60) return `${minutes}分钟前`

  const hours = Math.floor(deltaMs / HOUR_MS)
  if (hours < 24) return `${hours}小时前`
  if (hours < 48) return '昨天'

  const days = Math.floor(deltaMs / DAY_MS)
  if (days < 7) return `${days}天前`
  if (days < 30) return `${Math.max(1, Math.floor(days / 7))}周前`
  if (days < 365) return `${Math.max(1, Math.floor(days / 30))}个月前`

  return `${Math.max(1, Math.floor(days / 365))}年前`
}
