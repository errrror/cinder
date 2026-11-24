---
kind: downstream-contract
scope: keymgr-castellan
status: draft
origin: generated
source_paths: [cinder/keymgr/conf_key_mgr.py, cinder/volume/flows/api/create_volume.py]
symbols: [ConfKeyManager, ConfKeyManager._get_key, ConfKeyManager.create_key, ConfKeyManager.store, ConfKeyManager.get, ConfKeyManager.delete, ExtractVolumeRequestTask._get_encryption_key_id]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：密钥管理（castellan）

`cinder/keymgr/conf_key_mgr.py` 实现 castellan `key_manager.KeyManager` 接口，用配置中的固定十六进制密钥模拟密钥服务。外部黑盒：本仓未包含 castellan 后端与 Barbican 等外部 KMS 的服务端实现；本仓仅暴露 `ConfKeyManager` 这一本地实现。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 本仓业务封装文件 | `cinder/keymgr/conf_key_mgr.py`，`ConfKeyManager(key_manager.KeyManager)` | `cinder/keymgr/conf_key_mgr.py:57` |
| 外部接口 | `castellan.common.objects.symmetric_key` 与 `castellan.key_manager.key_manager` | `cinder/keymgr/conf_key_mgr.py:36-37` |
| 配置项 | `key_manager.fixed_key`（`cfg.StrOpt`，十六进制字符串，旧组 `keymgr`） | `cinder/keymgr/conf_key_mgr.py:45-52` |
| 固定密钥 ID | `'00000000-0000-0000-0000-000000000000'` | `cinder/keymgr/conf_key_mgr.py:78` |
| 密钥对象构造 | `symmetric_key.SymmetricKey('AES', len(key_bytes) * 8, key_bytes)` | `cinder/keymgr/conf_key_mgr.py:84-88` |
| 安全声明 | 单密钥实现不安全，初始化时只告警一次（`warning_logged` 类变量） | `cinder/keymgr/conf_key_mgr.py:66-72` |
| 成功判定 | `context is None` 一律 `NotAuthorized`；非本管理器 ID 一律拒绝 | `cinder/keymgr/conf_key_mgr.py:97-98`、`:108-113`、`:124-128` |

## 2. 本仓上游调用方反查表

| 封装方法 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `create_key` / `get` | `ExtractVolumeRequestTask._get_encryption_key_id` | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/flows/api/create_volume.py:357`、`:455-461` |
| `create_key` | 加密卷类型创建路径 | [卷领域模型](../../business/domain-models/volume.md) | `cinder/volume/flows/api/create_volume.py:455-461` |
| `_get_key` | 快照继承加密键场景 | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/flows/api/create_volume.py:457-461` |

## 3. 封装方法总清单

| 序号 | 封装函数签名 | 下游语义 | 读写类型 | 幂等 / 副作用 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `_get_key()` | 从配置解析 `SymmetricKey` | 读 | 每次新建对象 | `cinder/keymgr/conf_key_mgr.py:80-88` |
| 2 | `create_key(context, **kwargs)` | 创建密钥 | 写 | 恒返回固定 ID | `cinder/keymgr/conf_key_mgr.py:90-100` |
| 3 | `create_key_pair(context, **kwargs)` | 创建非对称密钥 | — | 直接 `NotImplementedError` | `cinder/keymgr/conf_key_mgr.py:102-104` |
| 4 | `store(context, managed_object, **kwargs)` | 注册密钥 | 写 | 仅允许固定密钥 | `cinder/keymgr/conf_key_mgr.py:106-115` |
| 5 | `get(context, managed_object_id)` | 取密钥 | 读 | 仅允许固定 ID | `cinder/keymgr/conf_key_mgr.py:117-130` |
| 6 | `delete(context, managed_object_id)` | 删除密钥 | 写 | 实际不删除，只告警 | `cinder/keymgr/conf_key_mgr.py:132-146` |

## 4. 逐方法请求字典与返回解包契约

### 4.1 `_get_key` 字典与密钥对象解包

| 组装字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `self.conf.key_manager.fixed_key` | `str` | 必填 | — | 为空抛 `ValueError`，提示配置项未定义 | `cinder/keymgr/conf_key_mgr.py:81-83` |
| `hex_key` | `str` | 必填 | — | 取 `fixed_key` 原值 | `cinder/keymgr/conf_key_mgr.py:84` |
| `key_bytes` | `bytes` | 必填 | — | `bytes(binascii.unhexlify(hex_key))` | `cinder/keymgr/conf_key_mgr.py:85` |
| `SymmetricKey` 参数一 | `str` | 固定 | `'AES'` | 算法字面量 | `cinder/keymgr/conf_key_mgr.py:86` |
| `SymmetricKey` 参数二 | `int` | 固定 | `len(key_bytes) * 8` | 由字节长度换算比特位数 | `cinder/keymgr/conf_key_mgr.py:87` |
| `SymmetricKey` 参数三 | `bytes` | 固定 | `key_bytes` | 解码后的原始密钥 | `cinder/keymgr/conf_key_mgr.py:88` |

### 4.2 各方法入参 / 返回 / 异常契约

| 封装方法 | 入参键（精确） | 返回值 | 异常 / 兜底 | 行号 |
|---|---|---|---|---|
| `create_key` | `context`、`**kwargs`（忽略） | `self.key_id` 固定 UUID | `context is None` → `NotAuthorized` | `cinder/keymgr/conf_key_mgr.py:90-100` |
| `create_key_pair` | `context`、`**kwargs` | 无 | `NotImplementedError("ConfKeyManager does not support asymmetric keys")` | `cinder/keymgr/conf_key_mgr.py:102-104` |
| `store` | `context`、`managed_object`、`**kwargs` | `self.key_id` | `managed_object != self._get_key()` → `KeyManagerError` | `cinder/keymgr/conf_key_mgr.py:106-115` |
| `get` | `context`、`managed_object_id` | `_get_key()` 返回的 `SymmetricKey` | `managed_object_id != self.key_id` → `KeyError` | `cinder/keymgr/conf_key_mgr.py:117-130` |
| `delete` | `context`、`managed_object_id` | `None` | 非固定 ID → `KeyManagerError`；合法 ID 只 `LOG.warning` | `cinder/keymgr/conf_key_mgr.py:132-146` |

### 4.3 编排层调用点解包

| 上游返回键 | 类型 | 转换逻辑 | 回填目标 | 行号 |
|---|---|---|---|---|
| `_get_encryption_key_id` 返回的 `encryption_key_id` | `str` | 由 `key_manager.create_key` 的固定 ID 或从快照/源卷继承 | `RequestSpec['encryption_key_id']` | `cinder/volume/flows/api/create_volume.py:455-461`、`:489` |

## 5. 符号级条件调用树

```text
ExtractVolumeRequestTask.execute -> cinder/volume/flows/api/create_volume.py:455
  └─ _get_encryption_key_id(key_manager, context, volume_type_id, snapshot, source_volume, image_meta)
       ├─ [无加密卷类型且无来源] cinder/keymgr/conf_key_mgr.py:90 create_key -> 固定 key_id
       ├─ [快照或源卷继承] cinder/keymgr/conf_key_mgr.py:117 get(managed_object_id) -> SymmetricKey
       └─ [guard] context 为空 -> cinder/keymgr/conf_key_mgr.py:97-98 NotAuthorized
  └─ [return] cinder/volume/flows/api/create_volume.py:489 'encryption_key_id': encryption_key_id
```

## 6. 共变耦合与修改清单

- **更换密钥后端**：实现新的 `key_manager.KeyManager` 子类并通过 castellan 的密钥管理器加载配置替换本实现；本仓 `ConfKeyManager` 的方法签名必须与 castellan 接口一致，否则编排层 `_get_encryption_key_id` 调用失败。
- **变更固定密钥格式**：修改 `fixed_key` 十六进制解析 (`cinder/keymgr/conf_key_mgr.py:81-88`) 需同步 [配置契约](../../contracts/configuration.md) 的 `key_manager` 组，并确认 AES 位宽由 `len(key_bytes) * 8` 推导。
- **隐式陷阱**：所有卷共享同一密钥，密钥泄露即全量可解 (`:28-31`)；`delete` 不真正删除 (`:132-146`)，`create_key_pair` 永久不支持 (`:102-104`)；`_get_key` 在 `fixed_key` 未配置时抛 `ValueError` 而非业务异常。
- **关联页面**：加密键的编排注入见 [拓扑映射](../topology-and-mapping.md)，消费 `encryption_key_id` 的后端见 [卷驱动插件层](storage-drivers.md)。
