---
kind: downstream-contract
scope: nova-compute-service
status: draft
origin: generated
source_paths: [cinder/compute/nova.py]
symbols: [novaclient, API._get_volume_extended_event, API._send_events, API.update_server_volume, API.create_volume_snapshot, API.delete_volume_snapshot, API.get_server, API.extend_volume]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：Nova 计算服务

`cinder/compute/nova.py` 通过 `novaclient` 与 Keystone 认证插件向 Nova 推送卷事件、协助卷快照、查询实例。外部黑盒：本仓未包含 `novaclient` 与 Nova 服务端实现，以下只记录本仓组装的事件字典与返回解包规则。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 本仓业务封装文件 | `cinder/compute/nova.py`，`API(base.Base)` | `cinder/compute/nova.py:170-171` |
| 底层传输 | `novaclient.client.Client`（外部 SDK） | `cinder/compute/nova.py:156-165` |
| 配置组 | `NOVA_GROUP = 'nova'`；注册 `region_name`、`interface`（默认 `public`）、`token_auth_url` 及 Keystone session/auth 选项 | `cinder/compute/nova.py:52-82` |
| 认证三分支 | `privileged_user` 且配置 auth_type → `load_auth_from_conf_options`；旧版 `os_privileged_user_*` → `identity.Password`；否则 → `identity.Token` | `cinder/compute/nova.py:121-149` |
| 客户端构造参数 | `api_version`、`session`、`insecure`、`timeout`、`region_name`、`endpoint_type`、`cacert`、`global_request_id`、`extensions` | `cinder/compute/nova.py:156-165` |
| 扩展白名单 | `discover_extensions` 仅保留 `assisted_volume_snapshots`、`list_extensions`、`server_external_events` | `cinder/compute/nova.py:86-92` |
| 成功判定 | 事件批量返回 `list`，逐元素 `code == 200`；非列表或缺失 `code` 记日志错误 | `cinder/compute/nova.py:188-203` |

## 2. 本仓上游调用方反查表

| 封装方法 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `API.extend_volume` | `VolumeManager._extend` → `nova_api.extend_volume(context, instance_uuids, volume.id)` | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/manager.py:2562` |
| `API.update_server_volume` | `VolumeManager` 迁移收尾 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/manager.py:2088` |
| `API.get_server` | `InstanceLocalityFilter` 查询实例所在主机 | [调度](../../business/scheduling.md) | `cinder/scheduler/filters/instance_locality_filter.py:105` |
| `API.create_volume_snapshot` | `Remotefs` 卷驱动辅助快照 | [备份与恢复](../../business/backup-restore.md) | `cinder/volume/drivers/remotefs.py:1456` |
| `API.delete_volume_snapshot` | `Remotefs` 卷驱动辅助快照删除 | [备份与恢复](../../business/backup-restore.md) | `cinder/volume/drivers/remotefs.py:1562` |

## 3. 封装方法总清单

| 序号 | 封装函数签名 | 下游目标方法 | 读写类型 | 幂等 / 重试 / 版本 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `novaclient(context, privileged_user=False, timeout=None, api_version=None)` | `Client(...)` 构造 | — | 每次调用新建客户端 | `cinder/compute/nova.py:107-167` |
| 2 | `API._send_events(context, events, api_version=None)` | `server_external_events.create(events)` | 写 | 异常仅记日志，不重抛 | `cinder/compute/nova.py:178-203` |
| 3 | `API.update_server_volume(context, server_id, src_volid, new_volume_id)` | `volumes.update_server_volume` | 写 | 无显式重试 | `cinder/compute/nova.py:212-217` |
| 4 | `API.create_volume_snapshot(context, volume_id, create_info)` | `assisted_volume_snapshots.create` | 写 | 依赖扩展白名单 | `cinder/compute/nova.py:219-225` |
| 5 | `API.delete_volume_snapshot(context, snapshot_id, delete_info)` | `assisted_volume_snapshots.delete` | 写 | 依赖扩展白名单 | `cinder/compute/nova.py:227-233` |
| 6 | `API.get_server(context, server_id, privileged_user=False, timeout=None)` | `servers.get(server_id)` | 读 | `NotFound` 转 `ServerNotFound` | `cinder/compute/nova.py:235-243` |
| 7 | `API.extend_volume(context, server_ids, volume_id)` | `server_external_events.create`，API 版本 `2.51` | 写 | 每 server 生成一个事件 | `cinder/compute/nova.py:245-249` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 `extend_volume` → 事件字典与返回解包

发往下游的组装字典表（`_get_volume_extended_event`，`cinder/compute/nova.py:173-176`）：

```json
{
  "name": "volume-extended",
  "server_uuid": "instance-uuid",
  "tag": "volume-uuid"
}
```

| 下游字典键 | 类型 | 必填条件 | 默认值 / 固定值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `name` | `str` | 必填 | 固定 `"volume-extended"` | 字面量 | `cinder/compute/nova.py:174` |
| `server_uuid` | `str` | 必填 | — | 遍历 `server_ids` 的单个 `server_id` | `cinder/compute/nova.py:175`、`:247-248` |
| `tag` | `str` | 必填 | — | `volume_id` 作为事件标签 | `cinder/compute/nova.py:176` |

| 返回键路径 | 类型 | 本仓提取、判空兜底与转换规则 | 行号 |
|---|---|---|---|
| `response` | `list[dict]` | 非 `list` 时记日志错误并 `return` | `cinder/compute/nova.py:188-190` |
| `response[i]['code']` | `int` | 缺失置 `response_error=True`；非 `200` 记警告；`200` 记 info | `cinder/compute/nova.py:192-203` |
| `nova_exceptions.NotFound` | 异常 | 记 warning，不重抛 | `cinder/compute/nova.py:183-184` |
| 其他 `Exception` | 异常 | `LOG.exception` 吞掉，卷扩展流程不因事件失败而回滚 | `cinder/compute/nova.py:185-186` |

### 4.2 其余封装方法字典契约

| 封装方法 | 下游调用参数（精确键） | 返回解包 / 异常翻译 | 行号 |
|---|---|---|---|
| `update_server_volume` | `server_id`、`src_volid`、`new_volume_id` 三个位置参数 | 无返回值 | `cinder/compute/nova.py:214-217` |
| `create_volume_snapshot` | `volume_id`、`create_info=create_info` | 无返回值 | `cinder/compute/nova.py:223-225` |
| `delete_volume_snapshot` | `snapshot_id`、`delete_info=delete_info` | 无返回值 | `cinder/compute/nova.py:231-233` |
| `get_server` | `servers.get(server_id)` | `NotFound` → `ServerNotFound(uuid=server_id)`；`Timeout` → `APITimeout(service='Nova')` | `cinder/compute/nova.py:237-243` |
| `has_extension` | `list_extensions.show_all()` | 返回 `extension in [e.name for e in nova_exts]`；`Timeout` → `APITimeout` | `cinder/compute/nova.py:205-210` |

## 5. 符号级条件调用树

```text
VolumeManager._extend -> cinder/volume/manager.py:2562 nova_api.extend_volume(context, instance_uuids, volume.id)
  └─ cinder/compute/nova.py:245 API.extend_volume
       ├─ api_version 固定 '2.51' -> cinder/compute/nova.py:246
       ├─ [遍历] cinder/compute/nova.py:247-248 _get_volume_extended_event(server_id, volume_id)
       │    -> {"name": "volume-extended", "server_uuid": server_id, "tag": volume_id}
       └─ cinder/compute/nova.py:178 _send_events(context, events, api_version='2.51')
            └─ cinder/compute/nova.py:182 nova.server_external_events.create(events)
                 └─ [解包] cinder/compute/nova.py:192-203 逐元素校验 code == 200
```

## 6. 共变耦合与修改清单

- **新增事件字段**：修改 `_get_volume_extended_event` (`cinder/compute/nova.py:173-176`) → 确认 Nova 事件接口是否接受该键（外部黑盒）→ 更新 [卷生命周期](../../business/volume-lifecycle.md) 事件说明 → 更新 `cinder/tests/unit/compute` 下的事件桩断言。
- **认证参数变更**：改 `novaclient` 的 Client 参数 (`:156-165`) 需同步 [配置契约](../../contracts/configuration.md) 的 `[nova]` 组与服务目录查询逻辑 (`:95-104`)。
- **隐式陷阱**：事件发送失败被吞掉，卷状态不会因 Nova 未收到事件而回退；`create_volume_snapshot`/`delete_volume_snapshot` 依赖 `assisted_volume_snapshots` 扩展存在，扩展白名单在模块导入时固化 (`:88-92`)。
- **关联页面**：卷事件的上游字段来源见 [拓扑映射](../topology-and-mapping.md)，镜像侧来源处理见 [Glance 镜像服务契约](glance.md)。
