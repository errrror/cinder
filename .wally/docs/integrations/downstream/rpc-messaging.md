---
kind: downstream-contract
scope: oslo-messaging-rpc-fanout
status: draft
origin: generated
source_paths: [cinder/rpc.py, cinder/common/constants.py, cinder/volume/rpcapi.py, cinder/scheduler/rpcapi.py, cinder/backup/rpcapi.py]
symbols: [RequestContextSerializer, RPCAPI, RPCAPI._get_cctxt, VolumeAPI.create_volume, SchedulerAPI.create_volume, SchedulerAPI.create_group, BackupAPI.create_backup, BackupAPI.import_record]
upstream: [integrations/topology-and-mapping.md, integrations/index.md]
downstream: []
---

# 下游出向接口契约：oslo.messaging RPC 扇出到 scheduler / volume / backup

`cinder/rpc.py` 提供传输层与序列化底座，三个 `rpcapi.py` 各自拼装业务 `msg_args` 字典，向 `cinder-scheduler`、`cinder-volume`、`cinder-backup` 三类服务发 `cast`（异步）或 `call`（同步）。外部黑盒：本仓未包含 oslo.messaging 传输实现，以下只记录本仓字典拼装与版本门控。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 底座文件 | `cinder/rpc.py`，`init` 创建 RPC 与通知两个 transport | `cinder/rpc.py:55-72` |
| 客户端构造 | `messaging.RPCClient(TRANSPORT, target, version_cap, serializer)` | `cinder/rpc.py:141-147` |
| 服务端构造 | `messaging.get_rpc_server(..., executor='eventlet', serializer, access_policy=DefaultRPCAccessPolicy)` | `cinder/rpc.py:150-159` |
| 上下文序列化 | `context.to_dict()`，有 profiler 时追加 `trace_info` 三键 `hmac_key`/`base_id`/`parent_id` | `cinder/rpc.py:119-130` |
| 上下文反序列化 | 弹出 `trace_info` → `profiler.init(**trace_info)` → `RequestContext.from_dict` | `cinder/rpc.py:132-138` |
| 实体序列化 | `CinderObjectSerializer(obj_version_cap)` 承载版本化对象 | `cinder/rpc.py:204-212` |
| 版本门控 | `assert_min_rpc_version` 检查 `can_send_version`，不满足抛 `ServiceTooOld` | `cinder/rpc.py:170-189` |
| 合法异常模块 | `ALLOWED_EXMODS = [cinder.exception.__name__]`，由 `get_allowed_exmods` 合并 | `cinder/rpc.py:49-52`、`:100-101` |

## 2. 三大下游 Target 对账表

| 下游服务 | TOPIC 常量 | 定义锚点 | RPCAPI 类 | 当前版本 / 默认版本 / BINARY |
|---|---|---|---|---|
| cinder-scheduler | `SCHEDULER_TOPIC = SCHEDULER_BINARY = 'cinder-scheduler'` | `cinder/common/constants.py:22`、`:25` | `SchedulerAPI` | `3.7` / `3.0` / `cinder-scheduler`，`cinder/scheduler/rpcapi.py:73-76` |
| cinder-volume | `VOLUME_TOPIC = VOLUME_BINARY = 'cinder-volume'` | `cinder/common/constants.py:23`、`:26` | `VolumeAPI` | `3.15` / `3.0` / `cinder-volume`，`cinder/volume/rpcapi.py:138-141` |
| cinder-backup | `BACKUP_TOPIC = BACKUP_BINARY = 'cinder-backup'` | `cinder/common/constants.py:24`、`:27` | `BackupAPI` | `2.1` / `2.0` / `cinder-backup`，`cinder/backup/rpcapi.py:51-54` |

## 3. 封装方法清单（扇出主路径）

| 封装方法 | 下游方法 | 调用方式 | 版本 / 扇出 | 定义锚点 |
|---|---|---|---|---|
| `SchedulerAPI.create_volume` | `create_volume` | `cast` | 默认版本，点对点 | `cinder/scheduler/rpcapi.py:94-101` |
| `SchedulerAPI.create_group` | `create_group` | `cast` | 默认版本，先 `jsonutils.to_primitive` | `cinder/scheduler/rpcapi.py:78-92` |
| `SchedulerAPI.migrate_volume` | `migrate_volume` / `migrate_volume_to_host` | `cast` | `3.3` / `3.0` 二选一 | `cinder/scheduler/rpcapi.py:103-120` |
| `SchedulerAPI.update_service_capabilities` | `update_service_capabilities` | `cast` | `fanout=True` | `cinder/scheduler/rpcapi.py:164-180` |
| `VolumeAPI.create_volume` | `create_volume` | `cast` | 默认版本，按 `service_topic_queue` 定向 | `cinder/volume/rpcapi.py:160-167` |
| `VolumeAPI.attach_volume` | `attach_volume` | `call` | `('3.3','3.0')`，低版本剔除 `volume` | `cinder/volume/rpcapi.py:196-207` |
| `VolumeAPI.publish_service_capabilities` | `publish_service_capabilities` | `cast` | `fanout=True` | `cinder/volume/rpcapi.py:237-239` |
| `BackupAPI.create_backup` | `create_backup` | `cast` | `server=backup.host` | `cinder/backup/rpcapi.py:56-59` |
| `BackupAPI.restore_backup` | `restore_backup` | `cast` | `server=volume_host` | `cinder/backup/rpcapi.py:61-65` |
| `BackupAPI.import_record` | `import_record` | `cast` | 五键字典 | `cinder/backup/rpcapi.py:80-90` |
| `BackupAPI.export_record` | `export_record` | `call` | 返回记录字典 | `cinder/backup/rpcapi.py:72-78` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 `SchedulerAPI.create_volume` → `msg_args`

| 下游字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `msg_args['snapshot_id']` | `str` | 可选 | `None` | 入参透传 | `cinder/scheduler/rpcapi.py:98` |
| `msg_args['image_id']` | `str` | 可选 | `None` | 入参透传 | `cinder/scheduler/rpcapi.py:99` |
| `msg_args['request_spec']` | `RequestSpec` | 必填 | — | 版本化对象，不经 `to_primitive` | `cinder/scheduler/rpcapi.py:100` |
| `msg_args['filter_properties']` | `dict` | 可选 | `None` | 含 `scheduler_hints` 子键 | `cinder/scheduler/rpcapi.py:100` |
| `msg_args['volume']` | `Volume` | 必填 | — | 入参对象，调用前 `volume.create_worker()` | `cinder/scheduler/rpcapi.py:96`、`:100` |

### 4.2 `SchedulerAPI.create_group` → `msg_args`

| 下游字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `msg_args['group']` | `Group` | 必填 | — | 入参对象 | `cinder/scheduler/rpcapi.py:86` |
| `msg_args['group_spec']` | `dict` | 可选 | — | `jsonutils.to_primitive(group_spec)` | `cinder/scheduler/rpcapi.py:84`、`:86` |
| `msg_args['request_spec_list']` | `list[dict]` | 可选 | — | 列表推导 `jsonutils.to_primitive(rs)` | `cinder/scheduler/rpcapi.py:82-83`、`:87` |
| `msg_args['group_filter_properties']` | `dict` | 可选 | `None` | 入参透传 | `cinder/scheduler/rpcapi.py:88` |
| `msg_args['filter_properties_list']` | `list[dict]` | 可选 | `None` | 入参透传 | `cinder/scheduler/rpcapi.py:89` |

### 4.3 `VolumeAPI.create_volume` 与兼容分支

| 下游字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `request_spec` | `RequestSpec` | 必填 | — | `cast` 关键字参数，非字典包裹 | `cinder/volume/rpcapi.py:164` |
| `filter_properties` | `dict` | 必填 | — | 同上 | `cinder/volume/rpcapi.py:165` |
| `allow_reschedule` | `bool` | 必填 | 入参 `True` | 克隆/快照绕调度时由调用方传 `False` | `cinder/volume/rpcapi.py:166` |
| `volume` | `Volume` | 必填 | — | 入参对象 | `cinder/volume/rpcapi.py:167` |
| `msg_args['volume']`（`attach_volume`） | `Volume` | 版本 ≥ 3.3 | 低版本 `pop` | `if not cctxt.can_send_version('3.3'): msg_args.pop('volume')` | `cinder/volume/rpcapi.py:204-207` |
| `backend_p['host']` / `['cluster_name']` / `['capabilities']`（`migrate_volume`） | `str`/`str`/`dict` | 版本 ≥ 3.5 | 低版本删 `cluster_name` | `cinder/volume/rpcapi.py:251-259` |

### 4.4 `BackupAPI` 写路径字典

| 封装方法 | 下游字典键（精确） | 调用方式 / 定向 | 行号 |
|---|---|---|---|
| `create_backup` | `backup`（`Backup` 对象） | `cast`，`server=backup.host` | `cinder/backup/rpcapi.py:56-59` |
| `restore_backup` | `backup`、`volume_id` | `cast`，`server=volume_host` | `cinder/backup/rpcapi.py:61-65` |
| `delete_backup` | `backup` | `cast`，`server=backup.host` | `cinder/backup/rpcapi.py:67-70` |
| `import_record` | `backup`、`backup_service`、`backup_url`、`backup_hosts` | `cast`，`server=host` | `cinder/backup/rpcapi.py:80-90` |
| `reset_status` | `backup`、`status` | `cast`，返回 `cast` 结果 | `cinder/backup/rpcapi.py:92-97` |
| `export_record` | `backup` | `call`，返回下游记录字典 | `cinder/backup/rpcapi.py:72-78` |

### 4.5 版本兼容与地址构造

| 规则 | 实现 | 行号 |
|---|---|---|
| `version=None` 时回落 `RPC_DEFAULT_VERSION`；元组走 `_compat_ver` 逐个探测 | `RPCAPI._get_cctxt` | `cinder/rpc.py:229-233` |
| 目标主机按 topic 后缀寻址，版本 ≥ 3.6 时 topic 由 `'%(topic)s.%(host)s'` 格式化为卷主题加主机名 | `VolumeAPI._get_cctxt` | `cinder/volume/rpcapi.py:143-158` |
| 最小服务版本从 `Service.get_minimum_rpc_version` 探测并缓存 | `determine_rpc_version_cap` | `cinder/rpc.py:235-251` |

## 5. 符号级条件调用树

```text
VolumeCastTask._cast_create_volume -> cinder/volume/flows/api/create_volume.py:730
  ├─ [无 source_volume_ref] cinder/scheduler/rpcapi.py:94 SchedulerAPI.create_volume
  │    ├─ volume.create_worker() -> :96
  │    ├─ msg_args = {snapshot_id, image_id, request_spec, filter_properties, volume} -> :98-100
  │    └─ cctxt.cast(ctxt, 'create_volume', **msg_args) -> :101
  └─ [有 source_volume_ref 且无 cgsnapshot_id] cinder/volume/rpcapi.py:160 VolumeAPI.create_volume
       ├─ _get_cctxt(volume.service_topic_queue) -> :162
       └─ cctxt.cast(ctxt, 'create_volume', request_spec=..., filter_properties=..., allow_reschedule=..., volume=...) -> :163-167
```

## 6. 共变耦合与修改清单

- **新增 `msg_args` 键**：改对应 `rpcapi.py` 字典组装（如 `cinder/scheduler/rpcapi.py:85-90`）→ 同步服务端 endpoint 签名（外部黑盒需联合验证）→ 更新 [拓扑映射](../topology-and-mapping.md) 的字段矩阵 → 更新 RPC 版本史与 `RPC_API_VERSION`。
- **版本兼容陷阱**：低版本必须 `pop` 新键或降级方法名，否则触发服务端未知参数；`assert_min_rpc_version` 在客户端直接抛 `ServiceTooOld`，不会降级成 `cast`。
- **对象传输陷阱**：`request_spec` 在 scheduler rpcapi 的 `create_volume` 中以对象直传，但 `create_group`/`migrate_volume` 先 `jsonutils.to_primitive`；新增对象字段时须确认两条路径的序列化差异。
- **关联页面**：扇出上层见 [拓扑映射](../topology-and-mapping.md)；落库结果见 [数据库 DAO 契约](sqlalchemy-db.md)；备份下游见 [Swift 备份后端](swift-backup.md)。
