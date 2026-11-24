---
kind: downstream-contract
scope: glance-image-service
status: draft
origin: generated
source_paths: [cinder/image/glance.py, cinder/volume/flows/api/create_volume.py]
symbols: [get_api_servers, GlanceClientWrapper.call, GlanceImageService.detail, GlanceImageService.show, GlanceImageService.create, _extract_attributes, _translate_from_glance, _translate_to_glance]
upstream: [integrations/index.md, integrations/topology-and-mapping.md]
downstream: []
---

# 下游出向接口契约：Glance 镜像服务

`cinder/image/glance.py` 通过 `glanceclient` 访问镜像服务，承担卷创建时的镜像元数据读取、`copy_volume_to_image` 结果回写。外部黑盒：本仓未包含 Glance 服务端实现，以下只记录本仓发起的请求字典与解包规则。

## 1. 封装定位与连接契约

| 契约项 | 精确值 / 规则 | 源码锚点（路径:行号） |
|---|---|---|
| 本仓业务封装文件 | `cinder/image/glance.py` | `GlanceClientWrapper` + `GlanceImageService` 双层 |
| 底层传输 | `glanceclient.Client`（外部 SDK） | `cinder/image/glance.py:85-104` |
| 端点来源 | `CONF.glance_api_servers` 配置列表，为空则查 `CONF.glance_catalog_info` 服务目录 | `cinder/image/glance.py:107-144` |
| 端点轮转 | `random.shuffle` + `itertools.cycle((netloc, use_ssl))` | `cinder/image/glance.py:143-144` |
| 重试次数 | `num_attempts = 1 + CONF.glance_num_retries`，失败 `time.sleep(1)` | `cinder/image/glance.py:190-215` |
| 认证参数 | `keystone` 策略时 `token=context.auth_token`；HTTPS 时 `insecure`/`ssl_compression`/`cacert` | `cinder/image/glance.py:90-100` |
| 请求追踪 | `params['global_request_id'] = context.global_id` | `cinder/image/glance.py:103` |
| 成功判定 | 方法正常返回；`ServiceUnavailable`/`InvalidEndpoint`/`CommunicationError` 重试后抛 `GlanceConnectionFailed` | `cinder/image/glance.py:187-217` |

## 2. 本仓上游调用方反查表

| 封装方法 | 上游调用模块与函数 | 所属业务流 | 调用点锚点 |
|---|---|---|---|
| `_get_image_metadata` → `GlanceImageService.show` | `ExtractVolumeRequestTask._get_image_metadata` | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/flows/api/create_volume.py:195`、`:434-436` |
| `_get_image_volume_type` → `GlanceImageService.show` | `ExtractVolumeRequestTask._get_image_volume_type` | [卷生命周期](../../business/volume-lifecycle.md) | `cinder/volume/flows/api/create_volume.py:234`、`:448-450` |
| `GlanceImageService.create` | `copy_volume_to_image` 流程 | [拓扑映射](../topology-and-mapping.md) | `cinder/image/glance.py:344-354` |

## 3. 封装方法总清单

| 序号 | 封装函数签名 | 下游方法 | 读写类型 | 幂等 / 重试 | 定义锚点 |
|---|---|---|---|---|---|
| 1 | `GlanceClientWrapper.call(context, method, *args, **kwargs)` | 动态 `getattr(controller, method)` | 混合 | 最多 `1 + glance_num_retries` 次 | `cinder/image/glance.py:179-217` |
| 2 | `GlanceImageService.detail(context, **kwargs)` | `images.list` | 读 | 依赖 `call` 重试 | `cinder/image/glance.py:228-241` |
| 3 | `GlanceImageService.show(context, image_id)` | `images.get` | 读 | 同上 | `cinder/image/glance.py:263-274` |
| 4 | `GlanceImageService.download(context, image_id, data=None)` | `images.data` | 读 | 同上 | `cinder/image/glance.py:316-342` |
| 5 | `GlanceImageService.create(context, image_meta, data=None)` | `images.create` | 写 | 同上 | `cinder/image/glance.py:344-354` |
| 6 | `GlanceImageService.update(context, image_id, image_meta, data=None, purge_props=True)` | `images.upload` + `images.update` | 写 | 同上 | `cinder/image/glance.py:356-399` |
| 7 | `GlanceImageService.get_location(context, image_id)` | 版本 2 的 `images.get` | 读 | 同上 | `cinder/image/glance.py:276-300` |

## 4. 逐方法请求字典与响应解包契约

### 4.1 `GlanceClientWrapper.call` 通用信封

| 组装字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `version` | `str` | 可选 | `self.version` | `kwargs.pop('version', self.version)`，不随请求下发 | `cinder/image/glance.py:185` |
| `controller` | `str` | 可选 | `'images'` | `kwargs.pop('controller', 'images')`，决定 controller 对象 | `cinder/image/glance.py:196-197` |
| `*args` / `**kwargs` | `any` | 按方法 | — | 原样透传给底层 client 方法 | `cinder/image/glance.py:198` |

响应侧：`call` 不做事后拆包，直接返回底层方法的原始结果；镜像列表在 `GlanceImageService.detail` 内经 `_is_image_available` 过滤与 `_translate_from_glance` 二次转换（`cinder/image/glance.py:198`、`:236-241`）。

### 4.2 `detail` 查询参数字典与镜像属性解包

| 下游字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `filters` | `dict` | 可选 | v1 强制 `{'is_public': 'none'}` | `_extract_query_params` 从 accepted 白名单提取 | `cinder/image/glance.py:243-261` |
| `marker` / `limit` / `sort_key` / `sort_dir` | `str`/`int` | 可选 | 不传该键 | 仅在入参 `params` 含同名键时写入 | `cinder/image/glance.py:245-249` |

| 返回键路径 | 类型 | 解包规则 | 行号 |
|---|---|---|---|
| `images[]` | `list[Resource]` | `_is_image_available` 过滤后逐个 `_translate_from_glance` | `cinder/image/glance.py:236-241`、`:464-492` |
| `IMAGE_ATTRIBUTES` | `list[str]` | 全量键：`size`、`disk_format`、`owner`、`container_format`、`status`、`id`、`name`、`created_at`、`updated_at`、`deleted`、`deleted_at`、`checksum`、`min_disk`、`min_ram`、`protected`，v2 追加 `visibility`，v1 追加 `is_public` | `cinder/image/glance.py:538-552` |
| `deleted_at` / `checksum` | `datetime`/`str` | `deleted` 为假时 `deleted_at=None`；`status != 'active'` 时 `checksum=None` | `cinder/image/glance.py:556-562` |
| `properties` | `dict` | `getattr(image, 'properties', {})`；v1 模式下承接全部非基础属性 | `cinder/image/glance.py:564`、`:438-441` |
| `created_at` / `updated_at` / `deleted_at` | `datetime` | `timeutils.parse_isotime` 转日期对象 | `cinder/image/glance.py:495-500` |
| `properties.block_device_mapping` / `properties.mappings` | `dict` | `_json_loads` 将 JSON 字符串反序列化 | `cinder/image/glance.py:504-531` |

### 4.3 `create` / `update` 写请求字典

| 组装字典键 | 类型 | 必填条件 | 默认值 | 值来源与转换逻辑 | 行号 |
|---|---|---|---|---|---|
| `data` | `file-like` | `if data:` | 不传该键 | 直接塞入 `sent_service_image_meta` | `cinder/image/glance.py:348-349` |
| `image_meta` 展开键 | `any` | 必填 | — | `_translate_to_glance`：`_convert_to_string` 序列化 `block_device_mapping`/`mappings`，再 `_remove_read_only` 删 `status`/`updated_at`/`created_at`/`deleted_at` | `cinder/image/glance.py:449-462`、`:569-575` |
| `properties` | `dict` | v2 且非空 | 不传该键 | `image_meta.update(properties)` 后 `del image_meta['properties']` 扁平化 | `cinder/image/glance.py:456-460` |
| `purge_props` | `bool` | v1 | 入参值 | 仅 v1 写入 | `cinder/image/glance.py:368-369` |
| `remove_props` | `list[str]` | v2 且 `purge_props` | 差集 | `set(cur_props) - set(props_to_update)` | `cinder/image/glance.py:379-386` |
| `id` | `str` | 禁用 | — | `image_meta.pop('id', None)` 保证不可编辑字段不下发 | `cinder/image/glance.py:370-372` |

### 4.4 错误码拦截与翻译

| 下游条件 | 下游语义 | 本仓异常 | 行号 |
|---|---|---|---|
| `glanceclient.exc.Forbidden` / `Unauthorized` | 无权访问 | `ImageNotAuthorized` / `NotAuthorized` | `cinder/image/glance.py:592-611` |
| `glanceclient.exc.NotFound` | 镜像不存在 | `ImageNotFound` | `cinder/image/glance.py:596-597` |
| `glanceclient.exc.BadRequest` | 参数非法 | `Invalid` | `cinder/image/glance.py:598-599` |
| `glanceclient.exc.HTTPOverLimit` | 限流 | `ImageLimitExceeded` | `cinder/image/glance.py:216-217` |

## 5. 符号级条件调用树

```text
ExtractVolumeRequestTask.execute -> cinder/volume/flows/api/create_volume.py:434 _get_image_metadata(context, image_id, size)
  └─ GlanceImageService.show -> cinder/image/glance.py:266 _client.call(context, 'get', image_id)
       ├─ [guard] cinder/image/glance.py:270-271 _is_image_available 为假 -> ImageNotFound
       ├─ [v2] cinder/image/glance.py:423-441 schema 基础属性 + properties 自定义属性
       ├─ [v1] cinder/image/glance.py:443 _extract_attributes（15+1 键）
       └─ [return] cinder/image/glance.py:445-447 时间戳与 JSON 转换后的元数据字典
```

## 6. 共变耦合与修改清单

- **新增镜像属性透传**：修改 `_extract_attributes` 的 `IMAGE_ATTRIBUTES` (`cinder/image/glance.py:544-552`) → 同步 v2 schema 分支 `:431-441` → 更新 [卷生命周期](../../business/volume-lifecycle.md) 的镜像来源说明 → 更新 Mock 镜像对象夹具。
- **协议陷阱**：v1 必须注入 `filters.is_public = 'none'` 才能取到私有镜像；v2 自定义属性必须扁平化进 `image_meta`，且 `status`/时间戳等只读字段必须在写方向删除；`checksum` 仅在 `status == 'active'` 时有值。
- **外部黑盒边界**：Glance 服务端字段校验不在本仓，新增请求键前须以真实服务版本验证；本仓仅保证封装层字典拼装与异常翻译。
- **关联页面**：镜像来源的字段改写见 [拓扑映射](../topology-and-mapping.md)，实例侧事件回推见 [Nova 计算服务契约](nova.md)。
