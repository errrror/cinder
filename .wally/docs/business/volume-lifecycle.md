---
kind: workflow
scope: WF-01
status: draft
origin: generated
source_paths: [cinder/volume/api.py, cinder/volume/manager.py, cinder/volume/flows/api/create_volume.py, cinder/volume/flows/manager/create_volume.py, cinder/scheduler/rpcapi.py, cinder/objects/fields.py]
symbols: [API.create, API.delete, API.attach, API.detach, API._extend, API.migrate_volume, API.retype, API.copy_volume_to_image, API.create_snapshot, Manager.create_volume, Manager.delete_volume, Manager.extend_volume, Manager.migrate_volume, Manager._migrate_volume_generic, Manager.retype, Manager.create_snapshot, ExtractVolumeRequestTask, QuotaReserveTask, QuotaCommitTask, VolumeCastTask, OnFailureRescheduleTask, get_flow]
upstream: [business/index.md, contracts/api/v3-volumes.md]
downstream: [business/scheduling.md, business/quotas.md, business/domain-models/volume.md, integrations/downstream/nova.md, integrations/downstream/glance.md]
---

# WF-01 · 卷主生命周期（创建 / 删除 / 挂载 / 扩容 / 迁移 / retype）

卷生命周期由 API 层的条件更新守卫与 Taskflow 编排共同驱动：API 节点做准入校验、配额预留与状态 CAS，再通过 RPC cast 把实际驱动操作交给 cinder-volume 工作节点异步执行，最终产物是 `volumes` 表状态、`volume_attachment` 行、后端物理卷与配额用量。读本页前先明确边界：调度选后端见 [`business/scheduling.md`](../business/scheduling.md)，配额三阶段提交语义见 [`business/quotas.md`](../business/quotas.md)，字段权威字典见 [`business/domain-models/volume.md`](../business/domain-models/volume.md)。

## 1. 符号级端到端执行调用树

```text
Trigger: POST /v3/{project_id}/volumes -> cinder/volume/api.py:218 API.create(size, name, ..., group_snapshot, source_group)
  ├─ [策略] cinder/volume/api.py:226 check_policy(context, 'create_from_image' if image_id else 'create')
  ├─ [拒绝] cinder/volume/api.py:229 if source_replica -> raise InvalidInput (v1 复制已废弃)
  ├─ [校验] cinder/volume/api.py:244 if size and (not strutils.is_int_like(size) or int(size) <= 0) -> raise InvalidInput
  ├─ [校验] cinder/volume/api.py:251/263 if consistencygroup/group and type not in allowed types -> raise InvalidInput
  ├─ [校验] cinder/volume/api.py:275/286 source_volume/snapshot 的 type 不兼容且 _retype_is_possible=False -> raise InvalidInput
  ├─ [编排] cinder/volume/api.py:336 create_volume.get_flow(db, image_service, availability_zones, create_what, sched_rpcapi, volume_rpcapi)
  │    └─ cinder/volume/flows/api/create_volume.py:818 get_flow -> ExtractVolumeRequestTask -> QuotaReserveTask -> EntryCreateTask -> QuotaCommitTask -> VolumeCastTask
  │         ├─ cinder/volume/flows/api/create_volume.py:619 QuotaReserveTask.execute: limit_check(per_volume_gigabytes=size) 后 reserve({'volumes':1,'gigabytes':size})
  │         ├─ cinder/volume/flows/api/create_volume.py:641 QuotaReserveTask.revert: optional_args['is_quota_committed']=False 时 rollback
  │         └─ cinder/volume/flows/api/create_volume.py:730 VolumeCastTask._cast_create_volume: 有 group_id 时注入 request_spec['group_backend']
  │              └─ cinder/scheduler/rpcapi.py:94 create_volume -> cctxt.cast(ctxt, 'create_volume', ...)
  └─ [工作节点] cinder/volume/manager.py:583 Manager.create_volume -> cinder/volume/flows/manager/create_volume.py:982 get_flow
       ├─ cinder/volume/manager.py:624/627 有 snapshot_id/source_volid 时加 COORDINATOR.get_lock("<id>-delete_snapshot/delete_volume")
       ├─ cinder/volume/flows/manager/create_volume.py:57 OnFailureRescheduleTask: no_reschedule_types 命中则直接置 error
       └─ cinder/volume/manager.py:664 if not rescheduled -> self._update_allocated_capacity(volume)

Trigger: DELETE /v3/{project_id}/volumes/{id} -> cinder/volume/api.py:388 API.delete(force, unmanage_only, cascade)
  ├─ [无 host 短路] cinder/volume/api.py:397 if not volume.host -> reserve({'volumes':-1,'gigabytes':-size}) -> volume.destroy() -> commit -> return
  ├─ [冻结检查] cinder/volume/api.py:430 if not unmanage_only -> volume.assert_not_frozen()
  ├─ [CAS 守卫] cinder/volume/api.py:433 expected = {attach_status != attached, migration_status in AVAILABLE_MIGRATION_STATUS, consistencygroup_id None, group_id None}
  ├─ [非 force] cinder/volume/api.py:441 expected['status'] in ('available','error','error_restoring','error_extending','error_managing')
  ├─ [快照过滤] cinder/volume/api.py:448/451/458 cascade 时按 cgsnapshot/undeletable 过滤，否则 ~volume_has_snapshots_filter()
  ├─ [状态置位] cinder/volume/api.py:459 values={'status':'deleting','terminated_at':utcnow()}；unmanage_only→'unmanaging'；error_managing→'error_managing_deleting'
  ├─ [加密密钥] cinder/volume/api.py:503 if encryption_key_id is not None -> key_manager.delete()（不可逆）
  └─ [RPC] cinder/volume/api.py:514 volume_rpcapi.delete_volume -> cinder/volume/manager.py:685 Manager.delete_volume
       ├─ cinder/volume/manager.py:712 if attach_status == ATTACHED -> raise VolumeAttached
       └─ cinder/volume/manager.py:727 is_migrating = migration_status not in (None,'error','success') 决定是否跳过配额

Trigger: 挂载 / 扩容 / 迁移 / retype（API 同步守卫，RPC 异步执行）
  ├─ cinder/volume/api.py:728 API.attach: if status == 'maintenance' -> raise InvalidVolume；readonly == 'True' and mode != 'ro' -> raise InvalidVolumeAttachMode
  ├─ cinder/volume/api.py:1303 API._extend: expected status = 'in-use'(attached) else 'available'；size_increase <= 0 -> raise InvalidInput
  │    └─ cinder/volume/api.py:1356 reserve({'gigabytes': size_increase}) -> cinder/scheduler/rpcapi.py:78 extend_volume cast
  │         └─ cinder/volume/manager.py:2518 Manager.extend_volume: driver.extend_volume -> QUOTAS.commit 或 error_extending + rollback
  ├─ cinder/volume/api.py:1412 API.migrate_volume: Service.get_by_id(is_up=True, disabled=False) 校验目标；expected migration_status 可用且目标 host/cluster 不同
  │    └─ cinder/volume/manager.py:2283 Manager.migrate_volume: driver.migrate_volume 未 moved 则 cinder/volume/manager.py:2005 _migrate_volume_generic
  └─ cinder/volume/api.py:1551 API.retype: migration_policy in ('on-demand','never')；reserve_vol_type_only 预占新类型配额
       └─ cinder/volume/manager.py:2590 Manager.retype: volume_types_diff all_equal 时直接标记 retyped
```

## 2. 分阶段业务规则与精确判定表

> Agent 必读：以下阈值与布尔条件逐字取自源码 `if/else`，不得用近似描述替代。

| 阶段 | 负责函数（`路径:行号`） | 精确布尔条件 / 阈值常量 | 命中分支行为 | 状态或数据副作用 |
|---|---|---|---|---|
| 创建入参 | `API.create` (`cinder/volume/api.py:244`) | `size and (not strutils.is_int_like(size) or int(size) <= 0)` | 抛 `InvalidInput`（size 必须为正整数或正整数字符串） | 无写入，策略检查已先通过 |
| 创建 AZ | `API.create` (`cinder/volume/api.py:299-302`) | `availability_zones = {az['name'] for az in raw_zones} ∪ {CONF.storage_availability_zone}` | AZ 不属于集合时 Taskflow 抛 `InvalidAvailabilityZone`，API 刷新 AZ 缓存重试 | 创建失败无卷落库 |
| 源尺寸 | `ExtractVolumeRequestTask._extract_size` (`cinder/volume/flows/api/create_volume.py:148-178`) | `size < snapshot.volume_size` 或 `size < source_volume['size']` 或 `not isinstance(size, six.integer_types) or size <= 0` | 抛 `InvalidInput`；未提供 size 时回退为源卷/快照尺寸 | 拒绝创建 |
| 配额预留 | `QuotaReserveTask.execute` (`cinder/volume/flows/api/create_volume.py:619-639`) | `limit_check(per_volume_gigabytes=size)` 超限 → `VolumeSizeExceedsLimit`；`reserve` 超限 → `process_reserve_over_quota` | 预留回滚，卷不落库 | `reservations` 未生成 |
| 删除状态守卫 | `API.delete` (`cinder/volume/api.py:433-442`) | `expected` 要求未挂载、未迁移、无 group；非 force 时 `status in ('available','error','error_restoring','error_extending','error_managing')` | `conditional_update` 返回 False → `InvalidVolume` | 状态保持原值 |
| 删除级联 | `API.delete` (`cinder/volume/api.py:444-458`) | `cascade and force` 用 `~volume_has_snapshots_in_a_cgsnapshot_filter()`；`cascade and not force` 用 `~volume_has_undeletable_snapshots_filter()`；非 cascade 用 `~volume_has_snapshots_filter()` | 快照条件不满足 → 拒绝 | 子快照 status 置 `deleting` |
| 挂载只读 | `API.attach` (`cinder/volume/api.py:730-743`) | `status == 'maintenance'`；`readonly == 'True' and mode != 'ro'` | 分别抛 `InvalidVolume` / `InvalidVolumeAttachMode` | admin_metadata.readonly 补写 `'False'` |
| 扩容下限 | `API._extend` (`cinder/volume/api.py:1320-1326`) | `size_increase = int(new_size) - volume.size; size_increase <= 0` | 抛 `InvalidInput` | 状态先置 `extending`，失败时 `_roll_back_status` 复位 |
| 扩容配额 | `API._extend` (`cinder/volume/api.py:1356-1375`) | `reserve({'gigabytes': size_increase})` 超 `OverQuota` | 抛 `VolumeSizeExceedsAvailableQuota(requested, consumed, quota)`；`consumed = reserved + in_use` | `reservations is None` 时回滚状态 |
| 扩容完成 | `Manager.extend_volume` (`cinder/volume/manager.py:2533-2556`) | `driver.extend_volume` 抛异常 → status `error_extending` + `QUOTAS.rollback`；成功 → commit 且 `attachments` 为空取 `available` 否则 `in-use` | 有挂载时 `nova_api.extend_volume(context, instance_uuids, volume.id)` | size 更新为 `int(new_size)`，pool 统计加 `size_increase` |
| 迁移准入 | `API.migrate_volume` (`cinder/volume/api.py:1427-1454`) | `Service.get_by_id(is_up=True, disabled=False, backend_match_level='pool')` 失败 → `InvalidHost`；`expected` 含 `status in ('available','in-use')`、`replication_status in (None,'disabled')`、目标不同于源 | 抛 `InvalidVolume` | `migration_status='starting'`，`lock_volume` 时 available→`maintenance` |
| 通用迁移超时 | `Manager._migrate_volume_generic` (`cinder/volume/manager.py:2036-2056`) | `deadline = starttime + CONF.migration_create_volume_timeout_secs`；目标卷 `status == 'error'` 或 `now > deadline` | 调 `_clean_temporary_volume(clean_db_only=True)` 后抛 `VolumeMigrationFailed`；等待使用 `time.sleep(tries ** 2)` 退避 | 目标卷 `migration_status='target:<源卷 id>'` |
| retype 策略 | `API.retype` (`cinder/volume/api.py:1553-1557`) | `migration_policy and migration_policy not in ('on-demand','never')` | 抛 `InvalidInput` | 无写入 |
| retype 守卫 | `API.retype` (`cinder/volume/api.py:1598-1621`) | `status in ('available','in-use')`、无迁移、无 group、类型不同、`volume_qos_allows_retype(new_type_id)` | 失败先 `QUOTAS.rollback(reservations + old_reservations)` 再抛 `InvalidVolume` | 成功置 `status='retyping'`，记录 `previous_status` |
| retype 等价 | `Manager.retype` (`cinder/volume/manager.py:2655-2658`) | `volume_types.volume_types_diff(...)` 返回 `all_equal=True` | 置 `retyped=True`，不调用驱动改类型 | 仍处理配额与状态复位 |

## 3. 实体状态机与合法迁移约束

```mermaid
stateDiagram-v2
    [*] --> creating: 创建落库
    creating --> available: 驱动创建成功
    creating --> error: 调度或驱动失败
    available --> in-use: attach
    in-use --> available: detach
    available --> extending: _extend
    in-use --> extending: extend_attached_volume
    extending --> available: 扩容成功且无挂载
    extending --> in-use: 扩容成功且有挂载
    extending --> error_extending: 驱动异常或配额失败
    available --> retyping: retype
    in-use --> retyping: retype
    retyping --> available: 类型变更成功
    retyping --> error: 类型变更失败
    available --> deleting: delete
    error --> deleting: delete 非 force
    deleting --> [*]: 删除完成
```

- **不可违反的不变量 1**：删除只允许从 `cinder/volume/api.py:441` 枚举的 `('available','error','error_restoring','error_extending','error_managing')` 进入；`force=True` 才会跳过 status 判定，但 `attach_status`、`migration_status`、`group_id` 三项守卫在 `cinder/volume/api.py:433-437` 恒成立。
- **不可违反的不变量 2**：`extending` 的前置状态由 `attached` 参数唯一决定（`cinder/volume/api.py:1305-1308`），失败必须经 `_roll_back_status` 写回 `orig_status`（`cinder/volume/api.py:1311-1318`）；扩容是单调递增，`size_increase <= 0` 直接拒绝。
- **不可违反的不变量 3**：`migration_status` 与 `status` 正交；`lock_volume=True` 仅把 `available` 改为 `maintenance`（`cinder/volume/api.py:1465-1468`），`in-use` 卷状态不变。`target:<id>` 是目标卷专属迁移态，由 `cinder/volume/manager.py:2027` 写入。
- **附加枚举**：`attach_status` 的全部合法字面量来自 `cinder/objects/fields.py:151-161` 的 `VolumeAttachStatus`（`attached` / `attaching` / `detached` / `reserved` / `error_attaching` / `error_detaching` / `deleted`），与 `status` 不是同一字段，禁止混用。

## 4. 幂等、并发互斥与异常补偿回滚表

| 边界 / 故障场景 | 源码检测条件（`路径:行号`） | 保护 / 回滚 / 降级动作 |
|---|---|---|
| 从快照或源卷并发删除导致源消失 | `cinder/volume/manager.py:624-631`：`snapshot_id`/`source_volid` 存在 | `coordination.COORDINATOR.get_lock("<id>-delete_snapshot" 或 "<id>-delete_volume")` 包住整个 create flow |
| 创建失败后的重调度 | `cinder/volume/flows/manager/create_volume.py:57-98`：`no_reschedule_types` 列表 | 命中 `ImageCopyFailure` / `MetadataCopyFailure` / `VolumeNotFound` 等直接置 error，不再 cast 调度；否则 `_reschedule` 递增 `filter_properties['retry']['num_attempts']` 并重新 `scheduler_rpcapi.create_volume` |
| Taskflow 中途失败 | `cinder/volume/flows/api/create_volume.py:641-659`：`QuotaReserveTask.revert` | `is_quota_committed=False` 时 `QUOTAS.rollback`；已 commit 则跳过，避免二次回滚 |
| 扩容配额失败 | `cinder/volume/api.py:1347-1352`、`1376-1381` | `finally` 中 `if rollback` / `if reservations is None` 无条件 `_roll_back_status()`，覆盖非 OverQuota 异常 |
| 上传镜像失败 | `cinder/volume/api.py:1270-1277` | `image_service.create` 抛异常时以 `{'status': 'uploading'}` 为条件把 status 复位为 `previous_status` 并清空 `previous_status` |
| 删除加密卷 | `cinder/volume/api.py:503-512` | `key_manager.delete` 失败仅 `LOG.warning` / `LOG.exception`，卷删除继续；密钥丢失后卷不可解密 |
| 通用迁移目标卷创建失败 | `cinder/volume/manager.py:2043-2054` | 仅清 DB 记录（`clean_db_only=True`），不触碰源卷，源卷 `migration_status` 置 `error` |

## 5. 共变耦合与修改清单（Agent Co-Change Playbook）

- **修改本流程业务规则时必查联动点**：
  1. 入向参数与策略入口：`cinder/volume/api.py:218`（create）、`cinder/volume/api.py:388`（delete）、`cinder/volume/api.py:1551`（retype）；契约见 [`contracts/api/v3-volumes.md`](../contracts/api/v3-volumes.md)。
  2. 调度 RPC 投递与版本协商：`cinder/scheduler/rpcapi.py:94-127`（`create_volume` / `migrate_volume` / `retype`），下游消费见 [`business/scheduling.md`](../business/scheduling.md)。
  3. 配额预留/提交/回滚三件套：`cinder/volume/flows/api/create_volume.py:600-706`，语义见 [`business/quotas.md`](../business/quotas.md)。
  4. 状态枚举与 OVO 字段同步：`cinder/objects/fields.py:151-165` 与 `cinder/objects/volume.py:84-86`，字段字典见 [`business/domain-models/volume.md`](../business/domain-models/volume.md)。
  5. 通知与下游计算侧：`nova_api.extend_volume` 位于 `cinder/volume/manager.py:2558-2562`，下游契约见 [`integrations/downstream/nova.md`](../integrations/downstream/nova.md)；镜像上传见 `cinder/volume/api.py:1268-1269` 与 [`integrations/downstream/glance.md`](../integrations/downstream/glance.md)。
  6. 工作节点流任务名与 revert 策略：`cinder/volume/flows/manager/create_volume.py:57`、`208`、`237`、`328`、`354`、`982`，改动任务顺序需同步 Taskflow 依赖。
- **隐式陷阱**：`API.create` 的 `cgsnapshot`/`source_cg`/`group_snapshot`/`source_group` 分支会把 `sched_rpcapi` 与 `volume_rpcapi` 都置为 `None`（`cinder/volume/api.py:328-335`），此时 API flow 不含 `VolumeCastTask`，改调度逻辑必须排除这些创建路径。
