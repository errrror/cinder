---
kind: downstream-contract
scope: sqlalchemy-dao
status: draft
origin: generated
source_paths: [cinder/db/sqlalchemy/api.py, cinder/db/sqlalchemy/models.py]
symbols: [model_query, quota_reserve, volume_create, volume_get, volume_update, backup_create, backup_update, Volume, Backup]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：SQLAlchemy 数据库 DAO

`cinder/db/sqlalchemy/api.py` 是本仓唯一的持久化封装层，把编排层字典写入 ORM 模型并从查询结果解包 `model_update`；`cinder/db/sqlalchemy/models.py` 定义 `volumes`、`backups` 等表结构。数据库服务端为外部黑盒：本仓未包含数据库服务端实现，以下只记录 DAO 入参字典键与返回字段。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 本仓业务封装文件 | `cinder/db/sqlalchemy/api.py`，`model_query` 为所有读路径入口 | `cinder/db/sqlalchemy/api.py:274-310` |
| 会话来源 | `kwargs.get('session') or get_session()` | `cinder/db/sqlalchemy/api.py:283` |
| 软删除过滤 | `read_deleted`：`no`→`deleted=False`；`yes`→不加过滤；`only`→`deleted=True`；`int_no`→`deleted=0`；其他值抛异常 | `cinder/db/sqlalchemy/api.py:284-299` |
| 租户隔离 | `project_only` 且用户上下文时 `filter_by(project_id=...)`；`VolumeAttachment` 特殊走 `Volume.project_id` 联表 | `cinder/db/sqlalchemy/api.py:301-308` |
| 事务边界 | `with session.begin():` 包住新增与配额预留 | `cinder/db/sqlalchemy/api.py:1151`、`:1538`、`:5136` |
| 装饰器 | `@require_context`、`@_retry_on_deadlock`、`@handle_db_data_error`、`@require_admin_context` | `cinder/db/sqlalchemy/api.py:1144-1145`、`:1520-1521`、`:5156` |

## 2. 本仓上游调用方反查表

| DAO 方法 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `quota_reserve` | `QUOTAS.reserve` → 编排层配额任务 | [配额](../../business/quotas.md) | `cinder/volume/api.py:218-366` 关联的 flow |
| `volume_create` | `EntryCreateTask.execute` 经 `objects.Volume.create()` 落到 DAO | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/flows/api/create_volume.py:551-552` |
| `volume_update` | `Volume.save` / 驱动 `model_update` 回填 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/db/sqlalchemy/api.py:2501` |
| `backup_create` | `BackupAPI.create_backup` 服务端 | [备份与恢复](../../business/backup-restore.md) | `cinder/backup/rpcapi.py:56-59` |

## 3. 封装方法总清单

| 序号 | DAO 函数签名 | 读写类型 | 字典 / 返回值形态 | 定义锚点 |
|---|---|---|---|---|
| 1 | `model_query(context, model, *args, **kwargs)` | 读 | 返回 SQLAlchemy `Query` | `cinder/db/sqlalchemy/api.py:274-310` |
| 2 | `volume_create(context, values)` | 写 | `values` 字典 → `Volume` 对象 | `cinder/db/sqlalchemy/api.py:1520-1541` |
| 3 | `volume_get(context, volume_id)` | 读 | → `Volume` 对象 | `cinder/db/sqlalchemy/api.py:2091` |
| 4 | `volume_update(context, volume_id, values)` | 写 | `values` 字典 → 行数 | `cinder/db/sqlalchemy/api.py:2501` |
| 5 | `volume_destroy(context, volume_id)` | 写 | 软删除标记 | `cinder/db/sqlalchemy/api.py:1621` |
| 6 | `quota_reserve(context, resources, quotas, deltas, expire, until_refresh, max_age, project_id=None, is_allocated_reserve=False)` | 写 | 返回 `reservations` 列表 | `cinder/db/sqlalchemy/api.py:1144-1307` |
| 7 | `backup_create(context, values)` | 写 | `values` 字典 → `Backup` 对象 | `cinder/db/sqlalchemy/api.py:5128-5141` |
| 8 | `backup_update(context, backup_id, values)` | 写 | `fail_reason` 截断至 255 | `cinder/db/sqlalchemy/api.py:5146-5153` |
| 9 | `backup_destroy(context, backup_id)` | 写 | `status=DELETED`、`deleted=True` | `cinder/db/sqlalchemy/api.py:5157-5167` |

## 4. 逐方法请求字典与返回解包契约

### 4.1 `quota_reserve` 入参字典与返回解包

| 下游字典键 / 参数 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `context` | `RequestContext` | 必填 | — | 内部 `elevated()` 提权 | `cinder/db/sqlalchemy/api.py:1149` |
| `resources` | `dict[str, Resource]` | 必填 | — | 每项含 `sync` 字段名，用于选 `QUOTA_SYNC_FUNCTIONS` | `cinder/db/sqlalchemy/api.py:1193` |
| `quotas` | `dict[str, int]` | 必填 | — | 配额上限，仅 `>= 0` 参与超配额判断 | `cinder/db/sqlalchemy/api.py:1245-1247` |
| `deltas` | `dict[str, int]` | 必填 | — | 资源增量，键即 `work` 集合来源 | `cinder/db/sqlalchemy/api.py:1163` |
| `expire` | `datetime` | 必填 | — | 透传给 `_reservation_create` | `cinder/db/sqlalchemy/api.py:1276-1278` |
| `until_refresh` / `max_age` | `int` | 必填 | — | 控制 `_quota_usage_create` 的刷新节奏 | `cinder/db/sqlalchemy/api.py:1174`、`:1185-1188` |
| `project_id` | `str` | 可选 | `context.project_id` | 为空时回填 | `cinder/db/sqlalchemy/api.py:1152-1153` |
| `is_allocated_reserve` | `bool` | 可选 | `False` | 为真时改走 `quota_allocated_update`，`usage=None` | `cinder/db/sqlalchemy/api.py:1231-1233`、`:1262-1275` |

| 返回键路径 | 类型 | 判空 / 兜底 / 转换规则 | 行号 |
|---|---|---|---|
| `reservations` | `list[str]` | 每个元素是 `_reservation_create(...).uuid` | `cinder/db/sqlalchemy/api.py:1258-1280`、`:1307` |
| `usages[r].in_use` / `.reserved` | `int` | 刷新时由 `sync()` 返回的字典回填；`in_use < 0` 触发重新同步 | `cinder/db/sqlalchemy/api.py:1177-1180`、`:1215`、`:1295` |
| `exception.OverQuota(overs, quotas, usages)` | 异常 | `usages` 每项重组为 `in_use`/`reserved`/`allocated` 三键 | `cinder/db/sqlalchemy/api.py:1300-1305` |
| `unders` | `list[str]` | 增量导致用量为负时仅告警不抛错 | `cinder/db/sqlalchemy/api.py:1297-1299` |

### 4.2 `volume_create` / `backup_create` 值字典与返回

| 组装字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `values['volume_metadata']` | `list[VolumeMetadata]` | 必填 | — | `_metadata_refs(values.get('metadata'), models.VolumeMetadata)` | `cinder/db/sqlalchemy/api.py:1523-1524` |
| `values['volume_admin_metadata']` | `list[VolumeAdminMetadata]` | 仅管理员上下文 | 非管理员时删除该键 | `_metadata_refs(values.get('admin_metadata'), ...)` | `cinder/db/sqlalchemy/api.py:1525-1530` |
| `values['id']` | `str` | 可选 | `str(uuid.uuid4())` | 缺省生成 | `cinder/db/sqlalchemy/api.py:1533-1534` |
| `values['backup_metadata']` | `list[BackupMetadata]` | 必填 | — | `_metadata_refs(values.get('metadata'), models.BackupMetadata)` | `cinder/db/sqlalchemy/api.py:5130-5131` |
| `values['fail_reason']`（`backup_update`） | `str` | 可选 | — | `(values['fail_reason'] or '')[:255]` | `cinder/db/sqlalchemy/api.py:5147-5149` |

返回解包：`volume_create` 与 `backup_create` 均调用私有 `_volume_get` / `_backup_get` 并按 `values['id']` 回读对象（`cinder/db/sqlalchemy/api.py:1541`、`:5141`）；`backup_update` 在 0 行受影响时抛 `BackupNotFound` (`:5152-5153`)。

### 4.3 ORM 表字段契约：`volumes`

| 字段分组 | 精确列名 | 定义锚点 |
|---|---|---|
| 标识与归属 | `id`、`_name_id`、`ec2_id`、`user_id`、`project_id`、`cluster_name`、`host` | `cinder/db/sqlalchemy/models.py:243-265` |
| 规格与状态 | `size`、`availability_zone`、`status`、`attach_status`、`migration_status`、`bootable`、`multiattach` | `cinder/db/sqlalchemy/models.py:266-292` |
| 命名与时间戳 | `display_name`、`display_description`、`scheduled_at`、`launched_at`、`terminated_at` | `cinder/db/sqlalchemy/models.py:272-277` |
| 后端驱动回写 | `provider_location`、`provider_auth`、`provider_geometry`、`provider_id` | `cinder/db/sqlalchemy/models.py:279-282` |
| 来源与加密 | `snapshot_id`、`volume_type_id`、`source_volid`、`encryption_key_id` | `cinder/db/sqlalchemy/models.py:262`、`:284-286` |
| 分组与复制 | `consistencygroup_id`、`group_id`、`replication_status`、`replication_extended_status`、`replication_driver_data`、`previous_status` | `cinder/db/sqlalchemy/models.py:288-298` |

`name_id` 属性在 `_name_id` 为空时回落到 `id`，`name` 属性用 `CONF.volume_name_template % name_id` 生成（`cinder/db/sqlalchemy/models.py:246-256`）。

### 4.4 ORM 表字段契约：`backups`

| 字段分组 | 精确列名 | 定义锚点 |
|---|---|---|
| 标识与归属 | `id`、`user_id`、`project_id`、`volume_id`、`host`、`availability_zone` | `cinder/db/sqlalchemy/models.py:725-736` |
| 展示与容器 | `display_name`、`display_description`、`container`、`parent_id` | `cinder/db/sqlalchemy/models.py:737-740` |
| 状态与统计 | `status`、`fail_reason`、`size`、`object_count`、`num_dependent_backups` | `cinder/db/sqlalchemy/models.py:741-749` |
| 服务与时间戳 | `service_metadata`、`service`、`data_timestamp`、`restore_volume_id` | `cinder/db/sqlalchemy/models.py:743-752` |
| 临时资源 | `temp_volume_id`、`temp_snapshot_id`、`snapshot_id` | `cinder/db/sqlalchemy/models.py:747-750` |

`Backup.name` 由 `CONF.backup_name_template % self.id` 生成；`fail_reason` 经 `@validates` 截断到 255 字符（`cinder/db/sqlalchemy/models.py:727-729`、`:754-756`）。

## 5. 符号级条件调用树

```text
EntryCreateTask.execute -> cinder/volume/flows/api/create_volume.py:516
  ├─ volume_properties = {size, user_id, project_id, status='creating', attach_status,
  │                       encryption_key_id, display_description, display_name,
  │                       multiattach, bootable} -> :534-546
  ├─ volume_properties.update(kwargs) -> :550
  ├─ objects.Volume(context=context, **volume_properties).create() -> :551-552
  └─ 经版本化对象层落到 api.volume_create(context, values) -> cinder/db/sqlalchemy/api.py:1522
       ├─ values['volume_metadata'] = _metadata_refs(...) -> :1523
       ├─ [if admin] values['volume_admin_metadata'] = ... -> :1525-1528
       ├─ [if not values['id']] values['id'] = uuid4 -> :1533-1534
       ├─ volume_ref.update(values) -> :1535
       ├─ session.add(volume_ref) within session.begin() -> :1537-1539
       └─ [return] _volume_get(context, values['id']) -> :1541
```

## 6. 共变耦合与修改清单

- **新增卷字段**：改 ORM 列定义 (`cinder/db/sqlalchemy/models.py:240-312`) → 改 DAO `values` 组装与迁移脚本 → 同步 [卷领域模型](../../business/domain-models/volume.md) → 运行 `python3 -m pytest cinder/tests/unit/db`。
- **新增配额资源**：改 `deltas` 键与 `resources[...].sync` 映射 (`cinder/db/sqlalchemy/api.py:1163`、`:1193`) → 同步 [配额业务流](../../business/quotas.md) → 核对 `OverQuota.usages` 三键结构 (`:1301-1303`)。
- **隐式陷阱**：`model_query` 的 `read_deleted` 非法值直接抛裸 `Exception` (`:297-299`)；`backup_update` 未判空时静默返回，`volume_update` 的返回值语义不同；新增字段必须显式进 `_metadata_refs` 白名单，否则不会随对象持久化。
- **关联页面**：字段来源见 [拓扑映射](../topology-and-mapping.md)，异步落库的上游扇出见 [RPC 扇出契约](rpc-messaging.md)。
