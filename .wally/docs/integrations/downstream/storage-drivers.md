---
kind: downstream-contract
scope: volume-driver-plugin
status: draft
origin: generated
source_paths: [cinder/volume/driver.py, cinder/interface/util.py, cinder/interface/__init__.py, cinder/volume/configuration.py]
symbols: [VolumeDriver, ISCSIDriver, ISCSIDriver._get_iscsi_properties, ISCSIDriver.initialize_connection, volumedriver, get_volume_drivers, DriverInfo, Configuration, BackendGroupConfiguration]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：卷驱动插件层

`cinder/volume/driver.py` 定义所有后端驱动必须实现的 `VolumeDriver` 接口，`cinder/interface/*` 负责装饰器注册与发现，`cinder/volume/configuration.py` 负责按后端组注入配置。外部黑盒：本仓未包含具体存储阵列固件实现，以下只记录插件契约与 `connection_info` 字典。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 接口基类 | `VolumeDriver(ManageableVD, CloneableImageVD, ManageableSnapshotsVD, MigrateVD, BaseVD)` | `cinder/volume/driver.py:2114-2115` |
| 注册装饰器 | `_volume_register`、`_backup_register`、`_fczm_register` 三个全局列表 | `cinder/interface/__init__.py:17-19` |
| 装饰器实现 | `volumedriver(cls)` / `backupdriver(cls)` / `fczmdriver(cls)` 直接 append 类对象 | `cinder/interface/__init__.py:22-37` |
| 发现入口 | `get_volume_drivers` / `get_backup_drivers` / `get_fczm_drivers`，先 `_ensure_loaded` 再包装 `DriverInfo` | `cinder/interface/util.py:42-57` |
| 扫描目录 | `cinder/volume/drivers`、`cinder/backup/drivers`、`cinder/zonemanager/drivers` | `cinder/interface/util.py:44`、`:50`、`:56` |
| 驱动元信息 | `DriverInfo` 暴露 `cls`、`desc`、`class_name`、`class_fqn`、`version`、`ci_wiki_name`、`supported` | `cinder/interface/util.py:60-71` |
| 配置注入 | `Configuration` 依据 `config_group` 选择 `DefaultGroupConfiguration` 或 `BackendGroupConfiguration` | `cinder/volume/configuration.py:138-149` |
| 配置优先级 | 后端组 → `backend_defaults` 共享组；`__getattr__` 在后端值为 `None` 时回落到共享组 | `cinder/volume/configuration.py:128-135` |

## 2. 本仓上游调用方反查表

| 封装契约 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `VolumeDriver.create_volume` / `delete_volume` | `VolumeManager` 的 RPC 方法 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/driver.py:2119`、`:2133` |
| `VolumeDriver.initialize_connection` / `terminate_connection` | `VolumeManager.initialize_connection` → RPC `call` | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/driver.py:2216`、`:2222` |
| `ISCSIDriver.initialize_connection` | iSCSI 后端导出连接信息 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/driver.py:2650` |
| `get_volume_drivers` | 驱动列表与文档生成工具 | [配置契约](../../contracts/configuration.md) | `cinder/interface/util.py:42-45` |
| `create_zone_manager` 装饰器 | FC 驱动连接信息后处理 | [FC Zone Manager](zonemanager.md) | `cinder/interface/util.py:54-57` |

## 3. 封装方法总清单（接口方法分组）

| 分组 | 方法签名（接口分层） | 返回约定 | 定义锚点 |
|---|---|---|---|
| 卷生命周期 | `create_volume(volume)`、`delete_volume(volume)`、`extend_volume(volume, new_size)` | 无返回值或 `model_update` | `cinder/volume/driver.py:2119`、`:2133`、`:2150-2152` |
| 快照 | `create_snapshot(snapshot)`、`delete_snapshot(snapshot)`、`revert_to_snapshot(context, volume, snapshot)` | 无返回值 | `cinder/volume/driver.py:2136-2142`、`:2158-2167` |
| 克隆与迁移 | `create_volume_from_snapshot(volume, snapshot)`、`retype(context, volume, new_type, diff, host)` | `retype` 固定返回 `(False, None)` | `cinder/volume/driver.py:2122`、`:2197-2198` |
| 数据路径 | `ensure_export`、`create_export`、`remove_export`、`initialize_connection`、`terminate_connection` | `connection_info` 字典 | `cinder/volume/driver.py:2201-2228` |
| 一致性组 | `create_consistencygroup`、`delete_consistencygroup`、`update_consistencygroup` | `model_update`、`volumes_model_update` | `cinder/volume/driver.py:2233-2252`、`:2285-2327`、`:2329-2337` |
| 托管纳管 | `manage_existing`、`unmanage`、`manage_existing_snapshot`、`get_manageable_volumes` | 大小 / 列表 | `cinder/volume/driver.py:2154-2192` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 `ISCSIDriver._get_iscsi_properties` 返回字典

| 下游字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `target_discovered` | `bool` | 必填 | — | `provider_location` 存在为 `False`，否则发现后为 `True` | `cinder/volume/driver.py:2565-2577` |
| `target_portal` / `target_iqn` / `target_lun` | `str`/`str`/`int` | 必填 | — | `provider_location.split(" ")` 拆分得到 | `cinder/volume/driver.py:2579-2600` |
| `target_portals` / `target_iqns` / `target_luns` | `list` | 多 portal（`nr_portals > 1`） | 不写该键 | 列表按 portal 数复制 | `cinder/volume/driver.py:2594-2597` |
| `volume_id` | `str` | 必填 | — | `volume['id']` | `cinder/volume/driver.py:2602` |
| `auth_method` / `auth_username` / `auth_password` | `str` | `provider_auth` 非空 | 不写该键 | `auth.split()` 三段 | `cinder/volume/driver.py:2604-2610` |
| `physical_block_size` / `logical_block_size` | `str` | `provider_geometry` 非空 | 不写该键 | `geometry.split()` 两段 | `cinder/volume/driver.py:2612-2616` |
| `encrypted` | `bool` | 必填 | — | `volume.get('encryption_key_id', None) is not None` | `cinder/volume/driver.py:2618-2619` |

### 4.2 `initialize_connection` 返回信封

| 返回键路径 | 类型 | 值来源 | 行号 |
|---|---|---|---|
| `driver_volume_type` | `str` | 固定 `'iscsi'` | `cinder/volume/driver.py:2653`、`:2658` |
| `data` | `dict` | `_get_iscsi_properties` 返回的完整字典 | `cinder/volume/driver.py:2654`、`:2659-2666` |
| `data.target_iqns` / `data.target_portals` / `data.target_luns` | `list` | 多路径场景由驱动填充 | `cinder/volume/driver.py:2668-2686` |

### 4.3 一致性组 `model_update` 解包约定

| 返回键路径 | 类型 | 判空 / 兜底 / 转换规则 | 行号 |
|---|---|---|---|
| `model_update['status']` | `str` | `'error'` 时 manager 抛异常；成功时可返回 `None` | `cinder/volume/driver.py:2238-2250` |
| `volumes_model_update[i]['id']` / `['status']` | `str` | 字典列表由驱动构造，不能直接复用 ORM `Volume` 对象 | `cinder/volume/driver.py:2269-2275` |
| `update_consistencygroup` 三元组 | `tuple` | `model_update`、`add_volumes_update`、`remove_volumes_update` | `cinder/volume/driver.py:2329-2337` |

### 4.4 驱动配置键来源

| 配置访问方式 | 规则 | 行号 |
|---|---|---|
| `self.configuration` 的属性访问 | 由 `Configuration` shim 代理到后端组或共享组 | `cinder/volume/driver.py:2520`、`:2587-2592` |
| `Configuration.safe_get` | 选项不存在返回 `None` 而非抛 `NoSuchOptError` | `cinder/volume/configuration.py:62-66`、`:122-126` |
| `BackendGroupConfiguration._ensure_config_values` | 同时注册到 `backend_defaults` 与当前组，并把当前组默认值设为 `None` 以便判定是否显式设置 | `cinder/volume/configuration.py:97-111` |

## 5. 符号级条件调用树

```text
VolumeManager.initialize_connection -> cinder/volume/driver.py:2216 VolumeDriver.initialize_connection(volume, connector)
  └─ ISCSIDriver.initialize_connection -> cinder/volume/driver.py:2650
       ├─ cinder/volume/driver.py:2525 _get_iscsi_properties(volume, multipath=...)
       │    ├─ [if provider_location] cinder/volume/driver.py:2565 target_discovered=False
       │    ├─ [else] cinder/volume/driver.py:2498 _do_iscsi_discovery -> target_discovered=True
       │    └─ [if auth] cinder/volume/driver.py:2604-2610 写入 CHAP 三键
       └─ [return] {"driver_volume_type": "iscsi", "data": {...}}
```

## 6. 共变耦合与修改清单

- **新增连接信息键**：修改 `_get_iscsi_properties` (`cinder/volume/driver.py:2561-2621`) → 同步 `initialize_connection` 文档示例 (`:2650-2687`) → 校验 [FC Zone Manager](zonemanager.md) 对 `data.initiator_target_map` 的消费不受影响 → 更新驱动单测与 `python3 -m pytest cinder/tests/unit/volume/drivers`。
- **新增驱动接口方法**：在 `VolumeDriver` (`cinder/volume/driver.py:2114`) 提供默认实现或 `NotImplementedError` → 在 `cinder/interface/__init__.py:22-37` 确认注册装饰器 → 更新 [配置契约](../../contracts/configuration.md) 的驱动选项 → 刷新 `DriverInfo` 元信息断言 (`cinder/interface/util.py:60-71`)。
- **隐式陷阱**：`initialize_connection` 的 `data` 字典是多下游共享信封，新增键前必须确认消费端兼容；`retype` 默认 `(False, None)` 表示不支持，驱动未覆盖时 manager 按失败处理；配置优先级是后端组覆盖共享组，缺失配置会回落到 `backend_defaults`。
- **关联页面**：连接信息的上游编排见 [拓扑映射](../topology-and-mapping.md)，`connection_info` 的下游消费者见 [FC Zone Manager](zonemanager.md)。
