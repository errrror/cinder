---
kind: operations
scope: runbook-and-observability
status: draft
origin: generated
source_paths: [cinder/cmd/manage.py, cinder/api/middleware/fault.py, cinder/api/openstack/wsgi.py, cinder/api/middleware/auth.py, cinder/image/glance.py, cinder/compute/nova.py, cinder/backup/drivers/swift.py, cinder/service.py, etc/cinder/api-httpd.conf, cinder/volume/drivers/veritas/vrtshyperscale.py]
symbols: [GetLogCommands.errors, GetLogCommands.syslog, ServiceCommands.list, FaultWrapper._error, Fault._fault_names, CinderKeystoneContext.__call__, _send_events]
upstream: [contracts/error-codes.md, contracts/api-reference.md]
downstream: [operations/pitfalls-and-adr.md, operations/deployment-and-runtime.md]
---

# 可观测性信号与故障定位决策树（Agent Runbook）

本页汇总 Cinder 内建的日志/审计读取入口与「症状→根因」确定性排查路径。本仓**未提供独立 `/health` 端点**：API 存活可由版本发现 `GET /` 验证（`cinder/api/versions.py:131-136`），服务存活由 `cinder-manage service list` 的 `status` 字段判定（`cinder/cmd/manage.py:531-549`）。状态码语义见 [错误码字典](../contracts/error-codes.md)，日志目录与端口见 [部署、进程拓扑与持久化目录契约](deployment-and-runtime.md)。

## 1. 诊断信号读取入口表

| 信号类别 | 接口 / 磁盘文件位置 | 核心诊断字段 | 源码锚点（`路径:行号`） |
|---|---|---|---|
| API 存活 | `GET /` | `_KNOWN_VERSIONS` 全版本 JSON（HTTP 300） | `cinder/api/versions.py:131-136` |
| 服务状态 | `cinder-manage service list` | `status` = `enabled`/`disabled`（按 `svc.disabled`） | `cinder/cmd/manage.py:531-549` |
| 集群状态 | `cinder-manage cluster list` | `status` = `enabled`/`disabled`（按 `cluster.disabled`） | `cinder/cmd/manage.py:581-596` |
| 错误日志扫描 | `cinder-manage logs errors` | 遍历 `CONF.log_dir` 下 `*.log`，倒序找含 `" ERROR "` 的行 | `cinder/cmd/manage.py:416-438` |
| 系统日志 | `cinder-manage logs syslog N` | 从 `/var/log/syslog` 或 `/var/log/messages` 倒序取含 `cinder` 的条目 | `cinder/cmd/manage.py:440-465` |
| API 故障包络 | HTTP 响应体 | `{fault_name: {code, message}}`，413 含 `retryAfter` | `cinder/api/openstack/wsgi.py:1320-1355` |
| FaultWrapper 日志 | 运行日志 | `Caught error:` 后接异常类型与异常详情、`%(url)s returned with HTTP %(status)d` | `cinder/api/middleware/fault.py:46-58` |
| 请求上下文 | `req.environ['cinder.context']` | `user_id` 缺失时直接 401；`X-Service-Catalog` 非法 JSON→500 | `cinder/api/middleware/auth.py:84-114` |
| RPC 远端错误 | `messaging.RemoteError` | `exc_type`/`value` 白名单决定 400 还是透传 500 | `cinder/api/contrib/volume_actions.py:92-103` |
| Apache 访问/错误日志 | `/var/log/apache2/cinder.log`、`cinder_error.log` | mod_wsgi 部署的 `%(cu)t %M` 错误格式与访问延迟 `%D(us)` | `etc/cinder/api-httpd.conf:2-12` |
| 通知审计 | `rpc.get_notifier(...)` | `groups.reset_status.start/end`、`volume_type.*`、`group_type_specs.*` 等事件 | `cinder/api/v3/groups.py:89-108`、`cinder/api/contrib/types_manage.py:47-50` |
| 配置泄漏审计 | 启动日志 | 含 `_password`/`_key`/URI 型 `sql_connection` 的项打印为 `FLAG SET` | `cinder/service.py:647-659` |
| 存储降级标记 | 卷元数据 `DN_Resiliency` | 值为 `'degraded'` 表示副本降级 | `cinder/volume/drivers/veritas/vrtshyperscale.py:367-374`、`436-444` |

## 2. 症状 → 根因定位与修复决策树

### 症状 A：API 返回 401 / 403，客户端无法访问资源

1. 查 `cinder/api/middleware/auth.py:109-111`：若 `ctx.user_id is None`，说明 keystone 头未带 `X_USER_ID`/`X_USER`，返回 401；补齐鉴权头或改用 `noauth` pipeline（`etc/cinder/api-paste.ini:24-28`）。
2. 查 403 来源：`FaultWrapper` 对 `NotAuthorized` 映射 403（`cinder/api/openstack/wsgi.py:599-601`）；核对 `etc/cinder/policy.json:1-10` 的 `admin_or_owner`/`admin_api` 规则与操作所需策略键。
3. 检查 `X-Service-Catalog` 头是否为合法 JSON，非法会在 `cinder/api/middleware/auth.py:91-97` 直接 500。

### 症状 B：请求返回 500 且 explanation 为空

1. 这是 `FaultWrapper._error` 的 `safe=False` 默认行为（`cinder/api/middleware/fault.py:51-75`）：内部异常详情不回显；去日志搜 `Caught error:` 与 `returned with HTTP` 两条记录定位异常类型。
2. 若异常来自 Glance，核对翻译链 `cinder/image/glance.py:578-611`：重试耗尽→`GlanceConnectionFailed`(500)、`NotFound`→`ImageNotFound`(404)、`Forbidden`→`ImageNotAuthorized`(403)。
3. 若来自 Nova，核对 `cinder/compute/nova.py:208-209`、`240-243` 的超时/NotFound 翻译；`code != 200` 的事件仅告警不抛错（`:197-201`）。
4. 若来自 Swift 备份，核对 `cinder/backup/drivers/swift.py:281-282`、`311-312` 的 `socket.error`→`SwiftConnectionFailed`，以及 MD5 不一致→`InvalidBackup`（`:288-292`）。

### 症状 C：服务显示 down / 任务卡住

1. 执行 `cinder-manage service list`（`cinder/cmd/manage.py:531-549`）：`disabled` 为人工禁用；若仍判定 down，核对 `service_down_time` 默认 60 秒（`cinder/common/config.py:155-158`）与 RabbitMQ `5672` 连通性。
2. 执行 `cinder-manage logs errors`（`cinder/cmd/manage.py:416-438`）扫 `ERROR` 行；若无错误，查 `cinder-manage logs syslog`（`:440-465`）获取内核/驱动层信息。
3. 对卡住的清理任务，查 `cinder/api/v3/workers.py:81-97`：若 `resource_id` 在 DB 中查不到或多条，`InvalidInput` 会拒绝清理请求；先修正 worker 记录再重试。

### 症状 D：卷状态异常或升级后属性缺失

1. 管理员可用 `os-reset_status` 重置状态（`cinder/api/contrib/admin_actions.py:94-127`）；注意合法状态集合因资源而异（基类 `:45-51`、volume `:151-157`、backup `:302-304`）。
2. 重置会经 `db.worker_destroy` 清理失效的 cleanup worker 记录（`cinder/api/contrib/admin_actions.py:85-93`、`120-122`），避免残留任务反复触发。
3. 升级/迁移场景留意 `cinder/exception.py:256-257` 的 `UnavailableDuringUpgrade`（400），以及 [存量死代码与高危雷区](pitfalls-and-adr.md) 中 replication v1 参数快速失败。

决策路径调用树：

```text
告警/报错 -> 定位入口
  ├─ 4xx -> 查 cinder/api/openstack/wsgi.py:1323-1355 Fault._fault_names + policy.json
  ├─ 5xx -> 查 cinder/api/middleware/fault.py:46-58 日志 -> 下游翻译表 (error-codes.md)
  ├─ 服务 down -> cinder-manage service list (:531) + service_down_time (:155)
  └─ 状态异常 -> os-reset_status (:94) -> 校验 valid_status 子集
```

## 3. 审计与诊断信号边界

- 本仓无统一检索/用量审计 API；`used_limits` 扩展（`cinder/api/contrib/used_limits.py:59-63`）与 `limits` 接口（`cinder/api/v3/limits.py:27-53`）提供配额使用视图，事件型审计依赖 `oslo_messaging` 通知（`cinder/api/contrib/types_manage.py:47-50`、`cinder/api/v3/groups.py:89-108`）。
- `cinder-manage logs errors` 仅扫描 `CONF.log_dir` 下后缀为 `.log` 的文件（`cinder/cmd/manage.py:422-423`），日志文件需符合该命名约定才能被纳入。
- Apache 部署下业务访问日志落在 `cinder.log`，错误落在 `cinder_error.log`（`etc/cinder/api-httpd.conf:11-12`），与原生部署的 `CONF.log_dir` 路径不同，排障时需先确认启动方式。

## 4. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 改 Fault 包络 | `cinder/api/openstack/wsgi.py:1323-1355`、`cinder/api/middleware/fault.py:46-75` | 新增状态码若不加入 `_fault_names` 会退化为 `computeFault` 键；`safe` 误开会泄露内部信息 |
| 改日志脱敏 | `cinder/service.py:647-659`、`cinder/backup/drivers/swift.py:104-106` | 秘密项命名须含 `_password`/`_key` 才被自动脱敏；新增 secret 选项应设 `secret=True` |
| 改下游翻译 | `cinder/image/glance.py:578-611`、`cinder/compute/nova.py:208-243`、`cinder/backup/drivers/swift.py:281-312` | 翻译顺序与 `six.reraise` 堆栈保留决定排障可用性；同步更新 [错误码字典](../contracts/error-codes.md) |
| 改状态白名单 | `cinder/api/contrib/admin_actions.py:45-51`、`151-157`、`302-304` | 白名单是 reset 能否成功的硬约束，变更需通知运维并更新本节症状 D |
| 改诊断命令 | `cinder/cmd/manage.py:416-465`、`531-596` | `cinder-manage` 子命令由 `CATEGORIES`+反射生成（`cinder/cmd/manage.py:699-749`），新增方法即新增子命令 |

配置来源与默认值见 [配置项全集](../contracts/configuration.md)；容器日志与卷挂载见 [部署、进程拓扑与持久化目录契约](deployment-and-runtime.md)。
