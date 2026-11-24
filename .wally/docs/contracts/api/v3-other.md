---
kind: api-contract
scope: api-v3-other-and-legacy
status: draft
origin: generated
source_paths: [cinder/api/v3/backups.py, cinder/api/contrib/backups.py, cinder/api/v3/groups.py, cinder/api/v3/group_snapshots.py, cinder/api/v3/group_types.py, cinder/api/v3/group_specs.py, cinder/api/v3/clusters.py, cinder/api/v3/workers.py, cinder/api/v3/resource_filters.py, cinder/api/v1/router.py, cinder/api/v2/router.py]
symbols: [BackupsController.update, GroupsController.create, GroupsController.create_from_src, GroupSnapshotsController.create, GroupTypesController.create, GroupSpecsController.create, ClusterController.update, WorkerController.cleanup, ResourceFiltersController.index]
upstream: [contracts/api-reference.md]
downstream: [contracts/api/v3-volumes.md, contracts/error-codes.md, operations/pitfalls-and-adr.md]
---

# v3 其余资源与 v1/v2 资源逐接口参数字典

本页补齐 [入向接口总表](../api-reference.md) 中除 volumes/snapshots/attachments/messages/limits 之外的全部资源：v3 的 backups、groups、group_snapshots、group_types、group_specs、clusters、workers、resource_filters，以及 v1、v2 的 volumes/types/snapshots/limits/metadata。核心资源见 [v3 核心资源参数字典](v3-volumes.md)，各 Action 的逐条清单见 [扩展 Action 全集](extensions.md)，废弃路径见 [高危雷区与存量死代码](../../operations/pitfalls-and-adr.md)。

## 1. backups 备份资源

v3 `BackupsController` 继承 `cinder/api/contrib/backups.py` 的实现，仅覆写 `update`/`show`/`detail`/`_convert_sort_name`（`cinder/api/v3/backups.py:34-108`）。

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `POST /{project_id}/backups` | body: `backup.volume_id`(必填，缺→400)、`container`、`name`、`description`、`incremental`(默认 False)、`force`(默认 False)、`snapshot_id`、`metadata`(3.43+) | `backup_api.create`；`InvalidVolume/InvalidSnapshot/InvalidVolumeMetadata*`→400，`ServiceNotFound`→503 (`cinder/api/contrib/backups.py:129-176`) | `cinder/api/contrib/backups.py:129-176` |
| `GET /{project_id}/backups` | query: `name`→`display_name`、`status`、`volume_id` + 分页排序 | `get_all` + `summary_list` | `cinder/api/contrib/backups.py:70-123` |
| `GET /{project_id}/backups/detail` | 同上 | `detail_list` | `cinder/api/contrib/backups.py:74-123` |
| `GET /{project_id}/backups/{id}` | path: `id` | 3.18+ 附带 `os-backup-project-attr:project_id`（受 `backup_project_attribute` 策略控制，拒绝时静默跳过） (`cinder/api/v3/backups.py:69-86`) | `cinder/api/v3/backups.py:69-86` |
| `PUT /{project_id}/backups/{id}` | body: `backup.name`→`display_name`、`description`→`display_description`、`metadata`(3.43+)；非支持字段→400 | 3.9+ 生效 (`cinder/api/v3/backups.py:37-62`) | `cinder/api/v3/backups.py:37-62` |
| `DELETE /{project_id}/backups/{id}` | path: `id` | `backup_api.delete`，`InvalidBackup`→400，返回 202 | `cinder/api/contrib/backups.py:56-68` |
| `POST /{project_id}/backups/{id}/action` → `restore` | body: `restore.volume_id`、`restore.name` | `InvalidInput/InvalidVolume/InvalidBackup`→400，配额超限→413 带 `Retry-After:0` | `cinder/api/contrib/backups.py:178-211` |
| `POST /{project_id}/backups/{id}/action` → `export_record` | path: `id` | 导出备份记录 | `cinder/api/contrib/backups.py:213-228` |
| `POST /{project_id}/backups/action` → `import_record` | body: `backup-service`/`backup-record` | 导入备份记录 | `cinder/api/contrib/backups.py:230-266` |

## 2. groups / group_snapshots 一致性组

`GROUP_API_VERSION` 为 3.13（`cinder/api/v3/groups.py`），复制能力自 `GROUP_REPLICATION_API_VERSION` 起可用。

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `POST /{project_id}/groups` | body: `group.name`、`description`、`group_type`(必填，UUID 或名称)、`volume_types`(必填)、`availability_zone`；缺 `group_type`/`volume_types`→400；默认 cgsnapshot 类型→400 | `group_api.create`，返回 202 (`cinder/api/v3/groups.py:200-244`) | `cinder/api/v3/groups.py:200-244` |
| `GET /{project_id}/groups` | query: 过滤 + 分页排序 | `index`→`_get_groups(is_detail=False)` | `cinder/api/v3/groups.py:153-199` |
| `GET /{project_id}/groups/detail` | 同上 | `detail`→`_get_groups(is_detail=True)` | `cinder/api/v3/groups.py:158-199` |
| `GET /{project_id}/groups/{id}` | path: `id` | `show` + `_check_default_cgsnapshot_type` | `cinder/api/v3/groups.py:56-69` |
| `PUT /{project_id}/groups/{id}` | body: `group.name`/`description`/`add_volumes`/`remove_volumes` | `update` | `cinder/api/v3/groups.py:311-375` |
| `POST /{project_id}/groups/{id}/action` → `delete` | body: `delete.delete-volumes`(bool，strict) | `_delete`，`InvalidGroup`→400，返回 202 | `cinder/api/v3/groups.py:112-151` |
| `POST /{project_id}/groups/{id}/action` → `reset_status` | body: `reset_status.status`(必填) | `_reset_status`，`InvalidGroupStatus`→400，发 `groups.reset_status.*` 通知，返回 202；3.20+ | `cinder/api/v3/groups.py:71-110` |
| `POST /{project_id}/groups/action` → `create-from-src` | body: `create-from-src.name`、`description`、`group_snapshot_id` 与 `source_group_id`（二选一且互斥）、`source_replica`; 缺/同传→400 | `create_from_src`，返回 202 | `cinder/api/v3/groups.py:246-309` |
| `POST /{project_id}/groups/{id}/action` → `enable_replication` / `disable_replication` / `failover_replication` / `list_replication_targets` | body 依各 action（复制目标等） | 复制相关动作，均带 `GROUP_REPLICATION_API_VERSION` 门槛 | `cinder/api/v3/groups.py:376-481` |
| `POST /{project_id}/group_snapshots` | body: `group_snapshot.group_id`(必填)、`name`、`description` | `create_group_snapshot`；`InvalidGroup/InvalidGroupSnapshot/InvalidVolume`→400，返回 202 | `cinder/api/v3/group_snapshots.py:148-184` |
| `GET /{project_id}/group_snapshots`、`/detail`、`/{id}` | 过滤 + 分页排序 | index/detail/show | `cinder/api/v3/group_snapshots.py:55-145` |
| `DELETE /{project_id}/group_snapshots/{id}` | path: `id` | `delete` | `cinder/api/v3/group_snapshots.py:69-94` |
| `POST /{project_id}/group_snapshots/{id}/action` → `reset_status` | body: `reset_status.status` | `_reset_status`；`InvalidGroupSnapshotStatus`→400，发 `groupsnapshots.reset_status.*` 通知，返回 202；3.19+ | `cinder/api/v3/group_snapshots.py:186-227` |

## 3. group_types / group_specs

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `POST /{project_id}/group_types` | body: `group_type.name`(必填，非空)、`description`、`group_specs`、`is_public`(默认 True) | `group_types.create`；重名→409，找不到→404，返回 202；3.11+ | `cinder/api/v3/group_types.py:58-105` |
| `GET /{project_id}/group_types`、`/{id}` | query: `is_public` 解析 | index/show | `cinder/api/v3/group_types.py:189-264` |
| `PUT /{project_id}/group_types/{id}` | body: `group_type.name`/`description`/`is_public` | `update` | `cinder/api/v3/group_types.py:106-165` |
| `DELETE /{project_id}/group_types/{id}` | path: `id` | `delete` | `cinder/api/v3/group_types.py:166-188` |
| `GET /{project_id}/group_types/{group_type_id}/group_specs` | path: `group_type_id` | `index`，先 `_check_policy`/`_check_type` | `cinder/api/v3/group_specs.py:54-60` |
| `POST /{project_id}/group_types/{group_type_id}/group_specs` | body: `group_specs` 键值字典 | `group_type_specs_update_or_create` + `groupTypeSpecs` 通知；键名仅允许字母数字/下划线/点/冒号/连字符 | `cinder/api/v3/group_specs.py:62-81`、`146-151` |
| `PUT /{project_id}/group_types/{group_type_id}/group_specs/{id}` | body: 单键字典，键须等于 `id` | `update`；body 为空/键不匹配/多项→400 | `cinder/api/v3/group_specs.py:83-109` |
| `GET /{project_id}/group_types/{group_type_id}/group_specs/{id}` | path: `id` | `show`，不存在→404 | `cinder/api/v3/group_specs.py:111-124` |
| `DELETE /{project_id}/group_types/{group_type_id}/group_specs/{id}` | path: `id` | `delete`；`GroupTypeSpecsNotFound`→404，返回 202 | `cinder/api/v3/group_specs.py:126-144` |

## 4. clusters / workers / resource_filters

| 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|
| `GET /{project_id}/clusters` | query: `disabled`/`is_up`/`name`/`binary` 等 | `_get_clusters` → `ClusterList.get_all` | `cinder/api/v3/clusters.py:48-90` |
| `GET /{project_id}/clusters/detail` | 同上 | `detail` | `cinder/api/v3/clusters.py:56-90` |
| `GET /{project_id}/clusters/{id}?binary=cinder-volume` | path: `id`，query: `binary`(默认 `cinder-volume`) | `show` | `cinder/api/v3/clusters.py:36-46` |
| `PUT /{project_id}/clusters/{enable\|disable}` | path: `id` 必须为 `enable`/`disable`；body: `name`(必填)、`binary`(默认 `cinder-volume`)、`disabled_reason`(1–255)；非法 id→404 | `update` 置 `cluster.disabled` 并保存，3.23+ | `cinder/api/v3/clusters.py:92-139` |
| `POST /{project_id}/workers/cleanup` | body: `binary`(空/`cinder-volume`/`cinder-scheduler`)、`disabled`、`is_up`、`resource_type`、`resource_id`(UUID)、`service_id`/`cluster_name`/`host`、`until` | `_prepare_params` 校验键集与取值；`sch_api.work_cleanup` 返回 `cleaning`/`unavailable`；3.24+，返回 202 | `cinder/api/v3/workers.py:40-120` |
| `GET /{project_id}/resource_filters` | 无必填参数 | `index` 读取过滤资源清单（与 `etc/cinder/resource_filters.json` 对应），3.33+ | `cinder/api/v3/resource_filters.py:28-41`、`cinder/api/v3/router.py:191-194` |

控制流示例（worker 清理）：

```text
POST /{project_id}/workers/cleanup -> cinder/api/v3/workers.py:103-120 WorkerController.cleanup
  ├─ [policy] self.policy_checker(req, 'cleanup') (:106)
  ├─ [guard] _prepare_params (:40-99) -> 非法键/非法 binary/非 UUID resource_id -> InvalidInput(400)
  ├─ [db] resource_id 无 location_keys 时 db.worker_get_all (:81-97) -> 0 条或多条 -> InvalidInput(400)
  └─ [outbound] sch_api.work_cleanup (:115-116) -> {"cleaning": [...], "unavailable": [...]}
```

## 5. v1 / v2 资源逐接口参数字典

v1、v2 共享 v2 的 `limits`、`types`、`volume_metadata`、`snapshot_metadata` 实现（`cinder/api/v1/router.py:76-92`、`cinder/api/v2/router.py:51-94`）。

| 版本 | 接口 | 关键参数 | 行为与错误分支 | 源码锚点 |
|---|---|---|---|---|
| v1 | `POST /v1/{project_id}/volumes` | body: `volume.imageRef`；v2 创建后经 `_volume_v2_to_v1` 转换；`Invalid image` 保留 400，其余 400→422；body 非法→422 | `cinder/api/v1/volumes.py:107-127` |
| v1 | `PUT /v1/{project_id}/volumes/{id}` | body: `volume` 字典，非法→422；委托 v2 `update` | `cinder/api/v1/volumes.py:129-140` |
| v1 | `GET /v1/{project_id}/volumes`、`/detail`、`/{id}` | 分页/过滤 + `id` | `cinder/api/v1/volumes.py:89-105` |
| v1 | `GET/POST/DELETE/PUT /v1/{project_id}/snapshots...` | 委托 `cinder.api.v1.snapshots` | `cinder/api/v1/router.py:55-59` |
| v1/v2 | `GET /{ver}/{project_id}/limits` | query: `project_id`/`tenant_id` | `cinder.api.v2.limits` 的 `LimitsController.index` (`cinder/api/v2/limits.py:52-63`) |
| v1/v2 | `/{ver}/{project_id}/types` 及 `/{id}`（v2 另有 `/{id}/action`） | body: `volume_type.name`/`description`/`extra_specs`/`is_public`（types_manage Action 见扩展页） | `cinder/api/v1/router.py:51-53`、`cinder/api/v2/router.py:51-54` |
| v1/v2 | `/{ver}/{project_id}/volumes/{volume_id}/metadata` 及 `PUT .../metadata` | body: `metadata`；含 etag 校验与全量更新 | `cinder/api/v1/router.py:79-92`、`cinder/api/v2/router.py:81-94` |
| v1/v2 | `/{ver}/{project_id}/snapshots/{snapshot_id}/metadata` 及 `PUT .../metadata` | body: `metadata` | `cinder/api/v1/router.py:61-74`、`cinder/api/v2/router.py:66-79` |
| v2 | `POST /v2/{project_id}/volumes` | 与 v3 相同字段集，含 `source_replica` 快速失败、UUID 校验、`multiattach` 布尔解析 | `cinder/api/v2/volumes.py:174-274` |
| v2 | `PUT /v2/{project_id}/volumes/{id}` | body: `volume` 必填 | `cinder/api/v2/volumes.py:280-338` |

## 6. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 改 groups 必填字段 | `cinder/api/v3/groups.py:212-226`、`cinder/api/v3/group_snapshots.py:159-163` | `group_type`/`volume_types`/`group_id` 缺失均抛 400；校验顺序决定错误信息，改前确认调用方依赖 |
| 改复制动作 | `cinder/api/v3/groups.py:376-481` | 四个复制 Action 共享版本门槛；部分与已废弃的 replication v1 语义相邻，见 [存量死代码警示](../../operations/pitfalls-and-adr.md) |
| 改 worker 清理参数 | `cinder/api/v3/workers.py:38-99`、`etc/cinder/resource_filters.json` | `allowed_clean_keys` 与 `resource_type` 白名单需与 `cleanable.CinderCleanableObject` 同步，否则合法资源被拒 |
| 改 v1 错误映射 | `cinder/api/v1/volumes.py:107-140`、`cinder/api/v2/volumes.py:174-338` | v1 把多数 400 转 422，但 `Invalid image` 分支保留 400；改 v2 逻辑会连带改变 v1 对外码 |
| 新增备份字段 | `cinder/api/contrib/backups.py:139-165`、`cinder/api/v3/backups.py:37-62` | `metadata` 受 3.43 门槛控制，两处版本判断需一致；返回视图字段由 `_view_builder` 决定 |

接口总数与族谱见 [入向接口总表](../api-reference.md)；动作逐条清单见 [扩展 Action 全集](extensions.md)。
