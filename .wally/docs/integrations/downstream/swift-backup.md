---
kind: downstream-contract
scope: swift-backup-storage
status: draft
origin: generated
source_paths: [cinder/backup/drivers/swift.py]
symbols: [SwiftBackupDriver.initialize, SwiftObjectWriter.close, SwiftObjectReader.read, put_container, get_container_entries, get_object_writer, get_object_reader, delete_object, _generate_object_name_prefix]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：Swift 备份后端

`cinder/backup/drivers/swift.py` 的 `SwiftBackupDriver` 通过 `swiftclient.Connection` 把卷数据分块存为 Swift 对象。外部黑盒：本仓未包含 Swift 服务端与 `swiftclient` 实现，以下只记录本仓组装的连接参数、对象名前缀与请求/返回解包规则。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 本仓业务封装文件 | `cinder/backup/drivers/swift.py`，`@interface.backupdriver` 注册的 `SwiftBackupDriver` | `cinder/backup/drivers/swift.py:143-145` |
| 基类 | `chunkeddriver.ChunkedBackupDriver` | `cinder/backup/drivers/swift.py:144`、`:152-156` |
| 分块与 SHA 配置 | `CONF.backup_swift_object_size`、`CONF.backup_swift_block_size`、`CONF.backup_swift_container`、`CONF.backup_swift_enable_progress_timer` | `cinder/backup/drivers/swift.py:148-156` |
| 重试配置 | `swift_attempts = CONF.backup_swift_retry_attempts`、`swift_backoff = CONF.backup_swift_retry_backoff` | `cinder/backup/drivers/swift.py:160-162` |
| 认证分支 | `backup_swift_auth == 'single_user'` 走 Keystone 凭据；否则走预认证 URL + token | `cinder/backup/drivers/swift.py:165-219`、`:220-257` |
| 端点来源 | 配置 `backup_swift_auth_url` / `backup_swift_url` 为空时查服务目录 `keystone_catalog_info` / `swift_catalog_info` | `cinder/backup/drivers/swift.py:171-195`、`:221-246` |
| 成功判定 | `put_object` 返回 etag 与本地 `hashlib.md5` 一致，否则 `InvalidBackup` | `cinder/backup/drivers/swift.py:278-293` |

## 2. 本仓上游调用方反查表

| 封装方法 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `get_object_writer` / `get_object_reader` | `ChunkedBackupDriver` 的分块备份与恢复流程 | [备份与恢复](../../business/backup-restore.md) | `cinder/backup/drivers/swift.py:334-348` |
| `put_container` / `get_container_entries` | `ChunkedBackupDriver` 容器准备与对象枚举 | [备份与恢复](../../business/backup-restore.md) | `cinder/backup/drivers/swift.py:315-332` |
| `_generate_object_name_prefix` | 备份元数据中心生成 `container`/对象名 | [备份与恢复](../../business/backup-restore.md) | `cinder/backup/drivers/swift.py:357-365` |

## 3. 封装方法总清单

| 序号 | 封装函数签名 | 下游 Swift API | 读写类型 | 幂等 / 重试 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `SwiftBackupDriver.initialize()` | `swift.Connection(...)` 构造 | — | 连接重试由 `retries`/`starting_backoff` 控制 | `cinder/backup/drivers/swift.py:160-257` |
| 2 | `SwiftObjectWriter.close()` | `put_object(container, object_name, reader, content_length=...)` | 写 | MD5 校验 | `cinder/backup/drivers/swift.py:275-293` |
| 3 | `SwiftObjectReader.read()` | `get_object(container, object_name)` | 读 | `socket.error` → `SwiftConnectionFailed` | `cinder/backup/drivers/swift.py:307-313` |
| 4 | `put_container(container)` | `put_container(container)` | 写 | 已存在不报错 | `cinder/backup/drivers/swift.py:315-321` |
| 5 | `get_container_entries(container, prefix)` | `get_container(container, prefix=..., full_listing=True)` | 读 | 返回对象名列表 | `cinder/backup/drivers/swift.py:323-332` |
| 6 | `delete_object(container, object_name)` | `delete_object(container, object_name)` | 写 | 无显式重试 | `cinder/backup/drivers/swift.py:350-355` |
| 7 | `_generate_object_name_prefix(backup)` | 本地字符串拼装 | — | 时间戳粒度秒 | `cinder/backup/drivers/swift.py:357-365` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 `swift.Connection` 构造参数字典

**single_user 分支**（`cinder/backup/drivers/swift.py:209-219`）：

| 下游参数键 | 类型 | 值来源 | 行号 |
|---|---|---|---|
| `authurl` | `str` | `self.auth_url`（配置或服务目录） | `:210` |
| `auth_version` | `str` | `CONF.backup_swift_auth_version` | `:211` |
| `tenant_name` | `str` | `CONF.backup_swift_tenant` | `:212` |
| `user` / `key` | `str` | `CONF.backup_swift_user` / `CONF.backup_swift_key` | `:213-214` |
| `os_options` | `dict` | 可选键 `user_domain_name`、`project_domain_name`、`project_name` | `:200-208`、`:215` |
| `retries` / `starting_backoff` | `int` | `self.swift_attempts` / `self.swift_backoff` | `:216-217` |
| `insecure` / `cacert` | `bool`/`str` | `self.backup_swift_auth_insecure` / `CONF.backup_swift_ca_cert_file` | `:218-219` |

**预认证分支**（`cinder/backup/drivers/swift.py:251-257`）：

| 下游参数键 | 类型 | 值来源 | 行号 |
|---|---|---|---|
| `retries` / `starting_backoff` | `int` | `self.swift_attempts` / `self.swift_backoff` | `:251`、`:254` |
| `preauthurl` | `str` | `self.swift_url`，配置为 `backup_swift_url + context.project_id` | `:240-241`、`:252` |
| `preauthtoken` | `str` | `context.auth_token` | `:253` |
| `insecure` / `cacert` | `bool`/`str` | 同 single_user 分支 | `:255-257` |

### 4.2 对象名与容器前缀字典

| 组装键 | 类型 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|
| `az` | `str` | `'az_%s' % self.az` | `cinder/backup/drivers/swift.py:359` |
| `backup_name` | `str` | `'%s_backup_%s' % (az, backup['id'])` | `cinder/backup/drivers/swift.py:360` |
| `volume` | `str` | `'volume_%s' % (backup['volume_id'])` | `cinder/backup/drivers/swift.py:361` |
| `timestamp` | `str` | `timeutils.utcnow().strftime("%Y%m%d%H%M%S")` | `cinder/backup/drivers/swift.py:362` |
| `prefix` | `str` | `volume + '/' + timestamp + '/' + backup_name` | `cinder/backup/drivers/swift.py:363` |
| `container` | `str` | `update_container_name` 原样返回传入容器名，不改写 | `cinder/backup/drivers/swift.py:367-369` |

### 4.3 对象写入 / 读取请求与解包

| 下游调用 | 组装参数 | 返回解包 / 校验 | 行号 |
|---|---|---|---|
| `put_object` | `container`、`object_name`、`reader = six.BytesIO(self.data)`、`content_length = len(self.data)` | 返回 `etag`；与 `hashlib.md5(self.data).hexdigest()` 比较，不等抛 `InvalidBackup` | `cinder/backup/drivers/swift.py:276-293` |
| `get_object` | `container`、`object_name` | 返回 `(_resp, body)`，本仓只取 `body` | `cinder/backup/drivers/swift.py:308-313` |
| `get_container` | `container`、`prefix`、`full_listing=True` | 取下标 `[1]` 的列表，逐元素读 `swift_obj['name']` | `cinder/backup/drivers/swift.py:326-332` |
| `delete_object` | `container`、`object_name` | 无返回值 | `cinder/backup/drivers/swift.py:352-355` |

| 下游条件 | 本仓异常 | 行号 |
|---|---|---|
| `socket.error`（写） | `SwiftConnectionFailed` | `cinder/backup/drivers/swift.py:281-282` |
| `socket.error`（读） | `SwiftConnectionFailed` | `cinder/backup/drivers/swift.py:311-312` |
| `socket.error`（列举 / 建容器 / 删对象） | `SwiftConnectionFailed` | `cinder/backup/drivers/swift.py:319-320`、`:329-330`、`:354-355` |
| etag 与 md5 不一致 | `InvalidBackup` | `cinder/backup/drivers/swift.py:288-292` |

## 5. 符号级条件调用树

```text
ChunkedBackupDriver 备份流程 -> cinder/backup/drivers/swift.py:334 get_object_writer(container, object_name)
  └─ SwiftObjectWriter.close -> cinder/backup/drivers/swift.py:275
       ├─ reader = six.BytesIO(self.data) -> :276
       ├─ etag = self.conn.put_object(container, object_name, reader, content_length=len(self.data)) -> :278-280
       ├─ [guard] socket.error -> SwiftConnectionFailed -> :281-282
       └─ [guard] etag != hashlib.md5(self.data).hexdigest() -> InvalidBackup -> :285-292
```

## 6. 共变耦合与修改清单

- **变更对象名布局**：修改 `_generate_object_name_prefix` (`cinder/backup/drivers/swift.py:357-365`) 会同时影响 `get_container_entries` 的 `prefix` 过滤 (`:323-332`) 与既有备份的恢复路径，必须保留旧前缀兼容读取。
- **变更连接参数**：改 `initialize` 的 `swift.Connection` 字典 (`:209-219`、`:251-257`) 需同步 [配置契约](../../contracts/configuration.md) 的 `backup_swift_*` 键，并核对 Keystone 服务目录解析 `keystone_catalog_info`/`swift_catalog_info` 的三段格式 (`:173-175`、`:223-225`)。
- **隐式陷阱**：对象名含秒级时间戳，同一秒内同名备份会覆盖；`get_extra_metadata` 固定返回 `None` (`:371-373`)，Swift 后端不携带额外元数据；`check_for_setup_errors` 在未配置 `backup_swift_url` 时只告警并返回 (`:375-384`)。
- **关联页面**：备份请求的字段来源见 [拓扑映射](../topology-and-mapping.md)，备份任务下发见 [RPC 扇出契约](rpc-messaging.md)。
