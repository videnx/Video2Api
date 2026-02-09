# rpaSora 接口文档（Apifox 项目 7778595）

## 文档信息
- 文档来源：`https://app.apifox.com/project/7778595`
- 采集时间：`2026-02-09`
- 项目名称：`rpaSora`
- 项目 ID：`7778595`
- 项目类型：`HTTP`
- 项目可见性：`private`
- 说明：本文档严格基于 Apifox 当前可见定义生成，不额外补造后端未声明的字段约束。

## 全局信息

### 鉴权
- 类型：`Bearer Token`
- 位置：请求头 `Authorization`
- 格式：`Authorization: Bearer <TOKEN>`
- 备注：Apifox 原定义包含明文 token，本文档已脱敏。

### 服务环境（Base URL）
| 环境 | Base URL |
|---|---|
| 开发环境 | `https://www.zzrj.fun:58000` |
| 测试环境 | `http://192.168.31.198:8000` |
| 正式环境 | `http://prod-cn.your-api-server.com` |

### 通用请求头
| Header | 是否必填 | 说明 |
|---|---|---|
| `Authorization` | 是 | `Bearer` 鉴权 |
| `Content-Type` | 建议 | `application/json` |

### 全局公共参数/安全方案
- `common-parameters`：未配置
- `security-schemes`：未配置（实际鉴权在接口级定义）

---

## 接口清单
| 名称 | 方法 | 路径 | API ID | 模块 |
|---|---|---|---:|---|
| 任务查询 | `GET` | `/v1/videos/1` | `413379076` | 默认模块 |
| 本地任务创建 | `POST` | `/v1/videos` | `413893632` | 默认模块 |

---

## 1. 本地任务创建

### 基本信息
- 名称：`本地任务创建`
- API ID：`413893632`
- 方法：`POST`
- 路径：`/v1/videos`
- 模块 ID：`7058986`
- 状态值：`-2`
- 创建时间：`2026-02-02T04:00:01.000Z`
- 更新时间：`2026-02-06T04:55:50.000Z`

### 请求定义

#### Path 参数
- 无

#### Query 参数
- 无

#### Header 参数
- 无自定义 Header 参数定义（仅接口鉴权要求 `Authorization`）

#### Cookie 参数
- 无

#### Request Body
- 必填：`true`
- Content-Type：`application/json`
- Schema（原始定义）：
```json
{
  "type": "object",
  "properties": {}
}
```
- 示例：
```json
{
  "prompt": "一只小猫和一只小狗再织毛衣",
  "image": null,
  "model": null
}
```

### 响应定义

#### 200 成功
- Content-Type：`json`
- Schema（原始定义）：
```json
{
  "type": "object",
  "properties": {}
}
```
- 响应头定义：无
- 示例：
```json
{
  "id": 50,
  "status": "pending",
  "message": "任务创建成功"
}
```

### 调用示例
```bash
curl -X POST "$BASE_URL/v1/videos" \
  -H "Authorization: Bearer $VIDEO2API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "一只小猫和一只小狗再织毛衣",
    "image": null,
    "model": null
  }'
```

---

## 2. 任务查询

### 基本信息
- 名称：`任务查询`
- API ID：`413379076`
- 方法：`GET`
- 路径：`/v1/videos/1`
- 模块 ID：`7058986`
- 状态值：`-2`
- 创建时间：`2026-01-30T09:43:50.000Z`
- 更新时间：`2026-02-06T04:56:11.000Z`

### 请求定义

#### Path 参数
- 无（当前文档路径写死 `1`）

#### Query 参数
- 无

#### Header 参数
- 无自定义 Header 参数定义（仅接口鉴权要求 `Authorization`）

#### Cookie 参数
- 无

#### Request Body
> 注：按 HTTP 语义，`GET` 通常不带请求体；但 Apifox 当前定义中该接口包含必填 body。此处按原定义保留。

- 必填：`true`
- Content-Type：`application/json`
- Schema（原始定义）：
```json
{
  "type": "object",
  "properties": {}
}
```
- 示例：
```json
{
  "prompt": "一只小猫和一只小狗再织毛衣",
  "image": null,
  "model": null
}
```

### 响应定义

#### 200 成功
- Content-Type：`json`
- Schema（原始定义）：
```json
{
  "type": "object",
  "properties": {}
}
```
- 响应头定义：无
- 示例（来自 Apifox responseExample）：
```json
{
  "id": "video_1",
  "object": "video",
  "status": "completed",
  "progress": 0,
  "progress_message": null,
  "created_at": 1769640435,
  "video_url": "https://videos.openai.com/...",
  "completed_at": 1769680826,
  "prompt": "一只可爱的小猫在草地上奔跑，阳光明媚，画面温馨"
}
```

### 调用示例
```bash
curl -X GET "$BASE_URL/v1/videos/1" \
  -H "Authorization: Bearer $VIDEO2API_TOKEN" \
  -H "Content-Type: application/json"
```

---

## 字段说明（基于示例）

### 请求体字段
| 字段 | 类型（示例） | 必填 | 说明 |
|---|---|---|---|
| `prompt` | `string` | 未声明 | 文本提示词 |
| `image` | `null` | 未声明 | 图像输入，类型未定义 |
| `model` | `null` | 未声明 | 模型参数，类型未定义 |

### 响应字段
| 字段 | 类型（示例） | 出现接口 | 说明 |
|---|---|---|---|
| `id` | `number` / `string` | 两个接口 | 创建返回数值 ID；查询返回视频 ID 字符串 |
| `status` | `string` | 两个接口 | 任务状态，如 `pending`、`completed` |
| `message` | `string` | 本地任务创建 | 创建结果消息 |
| `object` | `string` | 任务查询 | 对象类型，示例为 `video` |
| `progress` | `number` | 任务查询 | 任务进度 |
| `progress_message` | `null`/`string` | 任务查询 | 进度提示消息 |
| `created_at` | `number` | 任务查询 | 创建时间戳（秒级，按示例推断） |
| `video_url` | `string` | 任务查询 | 视频下载地址 |
| `completed_at` | `number` | 任务查询 | 完成时间戳（秒级，按示例推断） |
| `prompt` | `string` | 任务查询 | 最终任务提示词 |

---

## 已知限制与注意事项
- 当前两个接口都只定义了 `200` 成功响应，未定义 `4xx/5xx` 错误响应。
- 当前请求/响应 JSON Schema 均为空对象，字段约束依赖示例，建议后续补齐 schema。
- `GET /v1/videos/1` 路径为固定值，尚未参数化任务 ID。

## 原始接口链接
- 项目：<https://app.apifox.com/project/7778595>
- 任务查询详情：<https://api.apifox.com/api/v1/projects/7778595/http-apis/413379076?locale=zh-CN>
- 本地任务创建详情：<https://api.apifox.com/api/v1/projects/7778595/http-apis/413893632?locale=zh-CN>
- 环境列表：<https://api.apifox.com/api/v1/projects/7778595/environments?locale=zh-CN>
