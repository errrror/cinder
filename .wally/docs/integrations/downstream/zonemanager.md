---
kind: downstream-contract
scope: fc-zone-manager
status: draft
origin: generated
source_paths: [cinder/zonemanager/utils.py, cinder/zonemanager/fc_zone_manager.py, cinder/zonemanager/fczm_constants.py]
symbols: [create_zone_manager, create_lookup_service, get_formatted_wwn, add_fc_zone, remove_fc_zone, ZoneManager.add_connection, ZoneManager.delete_connection]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：FC Zone Manager

`cinder/zonemanager/*` 以装饰器方式拦截卷驱动的 `initialize_connection` / `terminate_connection` 返回值，在 Fabric 交换机上增删 FC Zone。外部黑盒：本仓未包含交换机固件与 `zone_driver` 外部 SDK 实现，以下只记录本仓消费的 `conn_info` 字典与调用链。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 本仓业务封装文件 | `cinder/zonemanager/utils.py`（装饰器与工厂）、`cinder/zonemanager/fc_zone_manager.py`（编排） | `cinder/zonemanager/utils.py:30-121` |
| 启用开关 | `config.safe_get('zoning_mode') == 'fabric'` 才创建 Zone Manager | `cinder/zonemanager/utils.py:32-36` |
| 默认域驱动 | `zone_driver = 'cinder.zonemanager.drivers.brocade.brcd_fc_zone_driver.BrcdFCZoneDriver'` | `cinder/zonemanager/fc_zone_manager.py:48-52` |
| 分区策略 | `zoning_policy` 默认 `'initiator-target'`，可选 `'initiator'` | `cinder/zonemanager/fc_zone_manager.py:53-56` |
| 查找服务 | `create_lookup_service` 同样受 `zoning_mode` 门控，返回 `FCSanLookupService` | `cinder/zonemanager/utils.py:54-64` |
| 初始化判定 | `ZoneManager.initialized` 为真才返回管理器，否则返回 `None` | `cinder/zonemanager/utils.py:37-47` |
| 字典键常量 | `IT_MAP='initiator_target_map'`、`DATA='data'`、`HOST='host_name'`、`STORAGE='storage_system'`、`SYSTEM='system'` | `cinder/zonemanager/fczm_constants.py:18-22` |

## 2. 本仓上游调用方反查表

| 封装方法 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `add_fc_zone` | FC 卷驱动的 `initialize_connection` 被装饰 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/zonemanager/utils.py:76-97` |
| `remove_fc_zone` | FC 卷驱动的 `terminate_connection` 被装饰 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/zonemanager/utils.py:100-121` |
| `ZoneManager.add_connection` | `add_fc_zone` 装饰器内调用 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/zonemanager/utils.py:93` |
| `ZoneManager.delete_connection` | `remove_fc_zone` 装饰器内调用 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/zonemanager/utils.py:117` |

## 3. 封装方法总清单

| 序号 | 封装函数签名 | 下游目标 | 读写类型 | 幂等 / 条件 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `create_zone_manager()` | `ZoneManager()` | — | `zoning_mode='fabric'` 且已初始化 | `cinder/zonemanager/utils.py:30-51` |
| 2 | `create_lookup_service()` | `FCSanLookupService()` | — | 同上门控 | `cinder/zonemanager/utils.py:54-64` |
| 3 | `get_formatted_wwn(wwn_str)` | 本地字符串处理 | — | 16 字符按两字符插冒号并转小写 | `cinder/zonemanager/utils.py:67-73` |
| 4 | `add_fc_zone(initialize_connection)` | `zm.add_connection(conn_info)` | 写 | `driver_volume_type=='fibre_channel'` 且含 `initiator_target_map` | `cinder/zonemanager/utils.py:76-97` |
| 5 | `remove_fc_zone(terminate_connection)` | `zm.delete_connection(conn_info)` | 写 | 同上条件 | `cinder/zonemanager/utils.py:100-121` |
| 6 | `ZoneManager.add_connection(conn_info)` | `self.driver.add_connection(fabric, map, host_name, storage_system)` | 写 | 未初始化时记日志并返回 | `cinder/zonemanager/fc_zone_manager.py:173-248` |
| 7 | `ZoneManager.delete_connection(conn_info)` | 域驱动删除接口 | 写 | 未初始化时记日志并返回 | `cinder/zonemanager/fc_zone_manager.py:250-279` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 装饰器消费的 `conn_info` 字典

| 下游字典键路径 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `conn_info` | `dict` | 必填 | — | 驱动 `initialize_connection` / `terminate_connection` 返回值；为空则记告警并返回 `None` | `cinder/zonemanager/utils.py:80-84`、`:104-108` |
| `conn_info['driver_volume_type']` | `str` | 必填 | `None` | 必须等于 `'fibre_channel'` 才继续 | `cinder/zonemanager/utils.py:86-87`、`:110-111` |
| `conn_info['data']` | `dict` | 必填 | — | 以 `'initiator_target_map' in conn_info['data']` 作为存在性判定 | `cinder/zonemanager/utils.py:88`、`:112` |
| `conn_info['data']['initiator_target_map']` | `dict[str, list[str]]` | 必填 | — | 每个发起端 WWN 映射到多个目标 WWN | `cinder/zonemanager/fczm_constants.py:18`；`cinder/zonemanager/fc_zone_manager.py:203-204` |
| `conn_info['data']['host_name']` | `str` | 可选 | 不传 | 存在时空格替换为下划线 | `cinder/zonemanager/fc_zone_manager.py:206-209` |
| `conn_info['data']['storage_system']` | `str` | 可选 | 不传 | 存在时空格替换为下划线 | `cinder/zonemanager/fc_zone_manager.py:211-215` |

### 4.2 `ZoneManager.add_connection` 解包与下游调用

| 下游参数 / 中间变量 | 类型 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|
| `initiator_target_map` | `dict` | `conn_info[zone_constant.DATA][zone_constant.IT_MAP]` | `cinder/zonemanager/fc_zone_manager.py:203-204` |
| `host_name` | `str`/`None` | 可选读取 `zone_constant.HOST`，`replace(" ", "_")` | `cinder/zonemanager/fc_zone_manager.py:206-209` |
| `storage_system` | `str`/`None` | 可选读取 `zone_constant.STORAGE`，`replace(" ", "_")` | `cinder/zonemanager/fc_zone_manager.py:211-215` |
| `fabric_map` | `dict` | `get_san_context(target_list)` 按目标 WWN 反查 fabric | `cinder/zonemanager/fc_zone_manager.py:222-225` |
| `valid_i_t_map` | `dict` | `get_valid_initiator_target_map({initiator: t_list}, True)` 过滤后的 I-T 映射 | `cinder/zonemanager/fc_zone_manager.py:231-235` |
| 域驱动调用 | — | `self.driver.add_connection(fabric, valid_i_t_map, host_name, storage_system)` | `cinder/zonemanager/fc_zone_manager.py:237-239` |

### 4.3 错误与空值兜底

| 条件 | 本仓处理 | 行号 |
|---|---|---|
| `ZoneManagerNotInitialized` | 记 error 并 `return`，不抛给调用方 | `cinder/zonemanager/fc_zone_manager.py:195-200`、`:272-277` |
| 其他 `Exception` | 包装为 `ZoneManagerException(reason=msg)` 抛出 | `cinder/zonemanager/fc_zone_manager.py:243-248` |
| `conn_info` 为空 | 记 warning 并返回 `None` | `cinder/zonemanager/utils.py:81-84`、`:105-108` |
| WWN 长度不等于 16 | 直接小写返回，不加冒号 | `cinder/zonemanager/utils.py:69-70` |

## 5. 符号级条件调用树

```text
FC 驱动 initialize_connection（被 cinder/zonemanager/utils.py:76 add_fc_zone 装饰）
  -> cinder/zonemanager/utils.py:80 先取得 conn_info
  ├─ [guard] cinder/zonemanager/utils.py:81-84 conn_info 为空 -> 返回 None
  ├─ [guard] cinder/zonemanager/utils.py:86-88 driver_volume_type != 'fibre_channel' 或无 IT_MAP -> 原样返回
  ├─ cinder/zonemanager/utils.py:30 create_zone_manager() -> zoning_mode='fabric' 时返回 ZoneManager
  └─ cinder/zonemanager/utils.py:93 zm.add_connection(conn_info)
       ├─ cinder/zonemanager/fc_zone_manager.py:203-215 解包 data.initiator_target_map / host_name / storage_system
       ├─ cinder/zonemanager/fc_zone_manager.py:223 get_san_context(target_list) -> fabric_map
       ├─ cinder/zonemanager/fc_zone_manager.py:232 get_valid_initiator_target_map(..., True)
       └─ cinder/zonemanager/fc_zone_manager.py:238 self.driver.add_connection(fabric, valid_i_t_map, host_name, storage_system)
```

## 6. 共变耦合与修改清单

- **新增 `conn_info.data` 消费键**：修改 `add_connection` / `delete_connection` 解包 (`cinder/zonemanager/fc_zone_manager.py:203-215`) → 同步 `cinder/zonemanager/fczm_constants.py:18-22` 常量 → 确认 [卷驱动插件层](storage-drivers.md) 的 `connection_info` 返回字典确实写入该键 → 更新 FC 驱动单测。
- **变更启用条件**：修改 `zoning_mode` 判定 (`cinder/zonemanager/utils.py:34`、`:57`) 需同步 [配置契约](../../contracts/configuration.md) 与驱动文档；`zone_driver` 与 `zoning_policy` 默认值变更需核对外部交换机驱动兼容性。
- **隐式陷阱**：装饰器只拦截 `fibre_channel` 类型且必须存在 `initiator_target_map`，否则静默跳过 zoning；`host_name`/`storage_system` 中的空格被替换为下划线，与交换机侧命名约定耦合；未初始化时仅记日志不阻断卷连接。
- **关联页面**：`conn_info` 的生产方见 [卷驱动插件层](storage-drivers.md)，连接调用的上游编排见 [拓扑映射](../topology-and-mapping.md)。
