---
kind: error-dict
scope: error-codes-and-translation
status: draft
origin: generated
source_paths: [cinder/exception.py, cinder/api/middleware/fault.py, cinder/api/openstack/wsgi.py, cinder/image/glance.py, cinder/backup/drivers/swift.py, cinder/compute/nova.py, cinder/volume/drivers/veritas/vrtshyperscale.py]
symbols: [CinderException, FaultWrapper._error, ExceptionContext.__exit__, Fault, _translate_image_exception, _translate_plain_exception, GlanceConnectionFailed, SwiftConnectionFailed]
upstream: [contracts/api-reference.md]
downstream: [operations/runbook-and-observability.md, contracts/api/v3-volumes.md]
---

# 错误码、异常传播与降级标识字典

本页全量归档 `cinder/exception.py` 中异常类到 HTTP 状态码的映射规则、下游错误翻译链路，以及 `degraded` / `reason` 等字面量。仓库共有 288 个异常类，全部继承 `CinderException`（`cinder/exception.py:76-143`）；状态码只由少数基类显式声明，其余通过继承获得。接口前缀与错误包络见 [入向接口总表](api-reference.md)，排查路径见 [可观测性信号与故障定位决策树](../operations/runbook-and-observability.md)。

## 1. 异常捕获与协议状态映射规则

| 边界位置（`路径:行号`） | 捕获的内部异常类型 | 映射后的对外状态码 / 错误结构 | 是否阻断写盘或重试 |
|---|---|---|---|
| `cinder/api/middleware/fault.py:77-82` (`FaultWrapper.__call__`) | 任意 `Exception` | 转 `_error`，`status = getattr(inner,'code',500)`；`status=None` 亦回落 500 (`cinder/api/middleware/fault.py:53-55`) | 终止请求，返回 Fault |
| `cinder/api/middleware/fault.py:46-75` (`_error`) | `QuotaError` 之外全部记 `LOG.exception`；`safe` 为真才回显异常名与 msg | `wsgi.Fault(outer)`；`outer` 由 `status_to_type` 按状态码构造 (`cinder/api/middleware/fault.py:38-44`) | 非安全异常 explanation 留空，防信息泄露 |
| `cinder/api/openstack/wsgi.py:595-620` (`ExceptionContext.__exit__`) | `NotAuthorized` | `Fault(HTTPForbidden)` (403) | 阻断访问 |
| `cinder/api/openstack/wsgi.py:602-606` | `Invalid`、`NotFound` | `Fault(ConvertedException(code=ex_value.code, explanation=...))` | 阻断写入 |
| `cinder/api/openstack/wsgi.py:607-611` | `TypeError` | `LOG.error` + `Fault(HTTPBadRequest())` (400) | 阻断写入 |
| `cinder/api/openstack/wsgi.py:612-617` | `Fault`、`webob.exc.HTTPException` | 透传 / 包成 `Fault` | 由具体异常决定 |
| `cinder/api/openstack/wsgi.py:1347-1355` (`Fault.__call__`) | 所有 Fault | `{fault_name: {code, message}}`；413 附加 `retryAfter` | 返回客户端 |
| `cinder/exception.py:50-69` (`ConvertedException`) | 用于承载任意 code | `title` 取 `status_reasons[code]`，未知取 `status_generic_reasons[code//100]` | 仅构造响应 |

`QuotaError` 在 `FaultWrapper._error` 中被单独排除在 `LOG.exception` 之外（`cinder/api/middleware/fault.py:47-48`），避免正常的配额拒绝刷错误日志。

## 2. 异常类 → HTTP 状态码全表

| 状态码 | 声明位置（`路径:行号`） | 声明类 | `safe` / headers | 代表子类（继承即得该码） |
|---|---|---|---|---|
| 400 | `cinder/exception.py:187-190` | `Invalid` | `safe=False` | `InvalidInput`(:209)、`InvalidVolume`(:225)、`InvalidSnapshot`(:192)、`InvalidUUID`(:277)、`MissingRequired`(:295)、`ValidationError`(:299)、`InvalidParameterValue`(:239)、`ServiceUnavailable`(:252)、`ImageTooBig`(:264) |
| 403 | `cinder/exception.py:166-169` | `NotAuthorized` | `safe=False` | `AdminRequired`(:171)、`PolicyNotAuthorized`(:175)、`ImageNotAuthorized`(:179) |
| 404 | `cinder/exception.py:326-329` | `NotFound` | `safe=True` | `VolumeNotFound`(:332)、`SnapshotNotFound`(:416)、`BackupNotFound`(:781)、`VolumeTypeNotFound`(:368)、`GroupNotFound`(:392)、`ServiceNotFound`(:449)、`ImageNotFound`(:445)、`WorkerNotFound`(:465)、`ClusterNotFound`(:484) |
| 405 | `cinder/exception.py:1331-1333` | `NotSupportedOperation` | 继承 `Invalid` | — |
| 413 | `cinder/exception.py:614-618` | `QuotaError` | `safe=True`、`headers={'Retry-After': '0'}` | `VolumeSizeExceedsAvailableQuota`(:621)、`VolumeSizeExceedsLimit`(:632)、`VolumeBackupSizeExceedsAvailableQuota`(:637)、`VolumeLimitExceeded`(:643)、`SnapshotLimitExceeded`(:652)、`BackupLimitExceeded`(:660)、`ImageLimitExceeded`(:664)、`GroupLimitExceeded`(:690)、`UnexpectedOverQuota`(:656) |
| 500 | `cinder/exception.py:84-87` | `CinderException` | `safe=False`、`code=500` | `VolumeBackendAPIException`(:145)、`VolumeDriverException`(:150)、`BackupDriverException`(:154)、`GlanceConnectionFailed`(:158)、`KeyManagerError`(:850)、`ReplicationError`(:872)、`LockCreationFailed`(:900) |
| 502 | `cinder/exception.py:316-319` | `RPCTimeout` | `safe=False` | — |

`Duplicate`（`cinder/exception.py:322-323`）与 `APIException`（`:303-309`）不声明 `code`，按继承落到 500；`Fault._fault_names`（`cinder/api/openstack/wsgi.py:1323-1332`）未覆盖的状态码统一使用 `computeFault` 键名。

## 3. 下游错误码 → 本仓错误翻译矩阵

| 下游系统 | 下游原始错误码 / HTTP 状态 | 本仓拦截位置（`路径:行号`） | 翻译后的本仓错误码 / 降级返回值 |
|---|---|---|---|
| Glance | `Forbidden` / `Unauthorized` | `cinder/image/glance.py:593-595` (`_translate_image_exception`) | `ImageNotAuthorized`（403） |
| Glance | `NotFound` | `cinder/image/glance.py:596-597` | `ImageNotFound`（404） |
| Glance | `BadRequest` | `cinder/image/glance.py:598-599` | `Invalid`（400） |
| Glance（通用） | `Forbidden`/`Unauthorized` | `cinder/image/glance.py:603-606` (`_translate_plain_exception`) | `NotAuthorized`（403） |
| Glance（通用） | `NotFound` | `cinder/image/glance.py:607-608` | `NotFound`（404） |
| Glance（通用） | `BadRequest` | `cinder/image/glance.py:609-610` | `Invalid`（400） |
| Glance | 可重试异常重试耗尽 | `cinder/image/glance.py:199-210` | `GlanceConnectionFailed(reason=e)`（500） |
| Glance | `HTTPOverLimit` | `cinder/image/glance.py:216-217` | `ImageLimitExceeded`（413） |
| Swift | `socket.error`（写对象/读对象） | `cinder/backup/drivers/swift.py:281-282`、`311-312` | `SwiftConnectionFailed(reason=err)`（500） |
| Swift | 上传对象 MD5 与本地不一致 | `cinder/backup/drivers/swift.py:288-292` | `InvalidBackup(reason=err)`（400） |
| Nova | `nova_exceptions.NotFound` | `cinder/compute/nova.py:240-241` | `ServerNotFound`（404） |
| Nova | `request_exceptions.Timeout` | `cinder/compute/nova.py:208-209`、`242-243` | `APITimeout(service='Nova')`（500） |
| Nova | `server_external_events.create` 返回非 list | `cinder/compute/nova.py:188-190` | 仅 `LOG.error`，不抛异常 |
| RPC | `messaging.RemoteError`（exc_type 白名单） | `cinder/api/contrib/volume_actions.py:92-103`、`120-130` | 白名单内转 400，其余原样抛（500） |

翻译入口 `_reraise_translated_image_exception` / `_reraise_translated_exception`（`cinder/image/glance.py:578-589`）用 `six.reraise(type(new_exc), new_exc, exc_trace)` 保留原始堆栈。

## 4. 控制器内即时状态码翻译示例

| 控制器位置 | 内部异常 | 对外状态码 |
|---|---|---|
| `cinder/api/v3/volumes.py:177-179` | `VolumeSnapshotNotFound` | 400（revert 无快照） |
| `cinder/api/v3/volumes.py:191-194` | `InvalidVolume` / `InvalidSnapshot` → 409；`VolumeSizeExceedsAvailableQuota` → 403 | 409 / 403 |
| `cinder/api/v3/volumes.py:231-237` | `source_replica` 旧参数 | `InvalidInput`（400） |
| `cinder/api/v3/attachments.py:181-192` | `CinderException` / 通用异常 → 500；`NotAuthorized` 透传 | 500 / 403 |
| `cinder/api/contrib/backups.py:166-173` | `InvalidVolume` 等 → 400；`ServiceNotFound` → 503 | 400 / 503 |
| `cinder/api/contrib/backups.py:200-207` | 配额类异常 → 413 + `Retry-After:0` | 413 |
| `cinder/api/contrib/volume_image_metadata.py:119-122` | `InvalidVolumeMetadataSize` → 413 | 413 |

## 5. 降级标识与 `reason` 字面量表

| 标识字符串字面量 | 产出位置（`路径:行号`） | 触发条件 | 系统自动兜底行为 |
|---|---|---|---|
| `'degraded'`（`DN_Resiliency` 元数据值） | `cinder/volume/drivers/veritas/vrtshyperscale.py:367-374`、`436-444` | 创建副本失败（`VolumeNotFound`/`UnableToProcessHyperScaleCmdOutput`/`ErrorInSendingMsg`）或副本数>1 时复制失败 | 不失败创建：仅创建一个副本，`reflection_target_ip=None`，元数据标记 `DN_Resiliency='degraded'`、`Secondary_datanode_*='NA'` |
| `reason`（异常构造关键字） | `cinder/exception.py:89-104` | 所有以 `reason` 为占位符的异常（如 `InvalidInput`、`GlanceConnectionFailed`、`SwiftConnectionFailed`） | `CinderException.__init__` 将 kwargs 格式化进 `message`，异常对象暴露 `.msg` 供 `FaultWrapper` 在 `safe=True` 时回显 |
| `code`（配额错误占位） | `cinder/exception.py:614-615` | 任一 `QuotaError` 子类抛出 | `message = 'Quota exceeded: code=%(code)s'`，HTTP 413 并带 `Retry-After:0` |

`degraded` 字面量在本仓仅出现在 Veritas HyperScale 驱动的副本弹性元数据中；其余业务链无统一 `degraded`/`reason` 状态字段，不得臆造。

## 6. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 修改异常 `code`/`safe` | `cinder/exception.py:84-87`、`166-190`、`326-329`、`614-618` | `safe=True` 会把内部 msg 暴露给客户端；`headers` 只在该异常经 `FaultWrapper` 时透传，控制器直接抛 `webob` 异常会丢失 `Retry-After` |
| 新增下游翻译分支 | `cinder/image/glance.py:578-611`、`cinder/compute/nova.py:235-243`、`cinder/backup/drivers/swift.py:281-312` | 翻译函数按 `isinstance` 顺序匹配，新分支须放在更宽泛分支之前；保留 `six.reraise` 的堆栈 |
| 改控制器状态码 | `cinder/api/v3/volumes.py:177-194`、`cinder/api/contrib/backups.py:166-207` | 与 [接口参数字典](api/v3-volumes.md) 中登记的响应码同步；413 必须带 `Retry-After` 才能进 `_fault_names` 的 `overLimit` 分支 |
| 改降级元数据 | `cinder/volume/drivers/veritas/vrtshyperscale.py:367-444` | `DN_Resiliency` 是被上层读取的约定键，改名会使监控漏报降级副本 |

符号映射与接口归属见 [入向接口总表](api-reference.md)，配置默认值见 [配置项、环境变量与动态开关全集](configuration.md)。
