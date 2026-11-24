---
kind: config-dict
scope: configuration
status: draft
origin: generated
source_paths: [cinder/__init__.py, cinder/volume/drivers/hitachi/vsp_utils.py, cinder/volume/drivers/hitachi/hbsd_fc.py, cinder/volume/drivers/hitachi/hbsd_iscsi.py, cinder/test.py, tox.ini, cinder/common/config.py, cinder/opts.py, cinder/volume/configuration.py, cinder/keymgr/conf_key_mgr.py, cinder/image/glance.py, cinder/backup/drivers/swift.py, cinder/exception.py]
symbols: [DefaultGroupConfiguration, BackendGroupConfiguration, Configuration, list_opts, set_middleware_defaults, key_mgr_opts, swiftbackup_service_opts, CONF.register_cli_opts]
upstream: [INDEX.md, overview/system-architecture.md]
downstream: [operations/deployment-and-runtime.md, contracts/error-codes.md]
---

# 配置项、环境变量与动态开关全集

本页覆盖全仓**非测试源码中全部 `os.environ` 写入与读取**（扫描 `cinder/`、`etc/`，共 7 处），以及测试/构建工具的 `setenv`/`getenv`，并登记关键 `cinder.conf` 配置项的默认值与覆盖优先级。所有默认值均来自 `cfg.*Opt` 声明，未声明默认值者记为「无（未设）」，不臆造。运行期目录与进程边界见 [部署、进程拓扑与持久化目录契约](../operations/deployment-and-runtime.md)，异常配置见 [错误码字典](error-codes.md)。

## 1. 配置覆盖优先级链

`命令行 --config-file 与具体选项参数` > `后端专属组（如 [volumes_backend] 显式值）` > `共享组 [backend_defaults]` > `DEFAULT 段` > `cfg.*Opt 代码默认值`（解析入口：`cinder/common/config.py:45` `CONF.register_cli_opts(core_opts)` 与 `cinder/common/config.py:218-219` `CONF.register_opts(core_opts/global_opts)`；后端回退逻辑见 `cinder/volume/configuration.py:74-135`）。

后端组读取顺序：`BackendGroupConfiguration.__getattr__` 先取 `backend_conf`，值为 `None` 时回退 `shared_backend_conf`（`cinder/volume/configuration.py:128-135`）；注册时先把所有 opt 注册进 `SHARED_CONF_GROUP='backend_defaults'`，再把后端组默认值改写为 `None` 以便判定是否被显式设置（`cinder/volume/configuration.py:97-111`、`116-117`）。

## 2. 进程环境变量全集（100% 扫描）

| 环境变量名 | 类型 | 代码默认值 | 必填 | 控制行为与边界影响 | 读取/写入锚点（`路径:行号`） |
|---|---|---|---|---|---|
| `EVENTLET_NO_GREENDNS` | str | 写入 `'yes'` | 否（进程强制写） | 关闭 eventlet 的 green DNS 解析，避免 monkey_patch 下的解析冲突；在包导入时即写入 | `cinder/__init__.py:18` |
| `LANG` | str | 写入 `'C'` | 否（驱动初始化写） | 强制 C  locale 以稳定 Hitachi 驱动对命令输出的解析；三处驱动各自写入 | `cinder/volume/drivers/hitachi/vsp_utils.py:576`、`cinder/volume/drivers/hitachi/hbsd_fc.py:60`、`cinder/volume/drivers/hitachi/hbsd_iscsi.py:68` |
| `OS_TEST_TIMEOUT` | int | `'0'`（不启用超时） | 否 | 单测全局超时秒数，>0 时挂 `fixtures.Timeout(..., gentle=True)`；非法值回落 0 | `cinder/test.py:132-139` |
| `OS_STDOUT_CAPTURE` | bool | 未设（False） | 否 | 为真时以 `StringStream('stdout')` 替换 `sys.stdout` | `cinder/test.py:143-147` |
| `OS_STDERR_CAPTURE` | bool | 未设（False） | 否 | 为真时以 `StringStream('stderr')` 替换 `sys.stderr` | `cinder/test.py:143-150` |
| `UPPER_CONSTRAINTS_FILE` | str | OpenStack upper-constraints URL | 否 | tox 安装依赖时的 `pip install -c` 约束文件路径 | `tox.ini:13` |
| `OS_TEST_PATH` | 路径 | 未设（默认单测路径） | 否 | tox `functional`/`compliance` 环境改写测试发现根目录 | `tox.ini:44`、`tox.ini:54` |
| `PYTHONHASHSEED` | str | `'0'`（tox setenv） | 否 | 固定哈希种子以稳定测试；注释说明随机种子尚未通过测试 | `tox.ini:7-10` |
| `PYTHONWARNINGS` | str | `default::DeprecationWarning`（tox setenv） | 否 | 显示弃用告警 | `tox.ini:11` |
| `VIRTUAL_ENV` | 路径 | `{envdir}`（tox setenv） | 否 | tox 虚拟环境目录 | `tox.ini:9` |
| `*_proxy` / `*_PROXY` | str | 继承宿主（tox passenv） | 否 | 代理设置透传进测试环境 | `tox.ini:28` |
| `MYSQL_ROOT_PASSWORD` | str | `password`（block-box 示例） | 容器编排必填 | mariadb 容器初始化 root 口令；仅用于本地容器演示 | `contrib/block-box/docker-compose.yml` |
| `INIT_DB` | str | `true`（cinder-api 容器示例） | 否 | block-box 的 init 脚本据此初始化数据库 | `contrib/block-box/docker-compose.yml` |

说明：源码中另有三处 `LOG` 与 `CONF` 读取，但不存在更多 `os.environ`/`getenv`/`putenv` 调用；密钥类配置统一走 `cfg.StrOpt(secret=True)`（如 `backup_swift_key`，`cinder/backup/drivers/swift.py:104-106`），不通过环境变量注入。

## 3. 关键 `cinder.conf` 配置项与默认值

### 3.1 核心与 API 开关（`cinder/common/config.py`）

| 配置键 | 类型 | 默认值 | 覆盖优先级 / 弃用状态 | 源码锚点 |
|---|---|---|---|---|
| `state_path` | StrOpt | `/var/lib/cinder` | CLI 注册；旧名 `pybasedir` | `cinder/common/config.py:40-45` |
| `my_ip` | HostAddressOpt | `netutils.get_my_ipv4()` | 默认取本机 IPv4 | `cinder/common/config.py:48-50` |
| `host` | HostAddressOpt | `socket.gethostname()` | 节点标识 | `cinder/common/config.py:116-120` |
| `enable_v1_api` | BoolOpt | `False` | 已标弃用；v1 默认关闭 | `cinder/common/config.py:85-88` |
| `enable_v2_api` | BoolOpt | `True` | 已标弃用 | `cinder/common/config.py:89-92` |
| `enable_v3_api` | BoolOpt | `True` | 当前主版本 | `cinder/common/config.py:93-95` |
| `api_rate_limit` | BoolOpt | `True` | 速率限制开关 | `cinder/common/config.py:96-98` |
| `osapi_volume_extension` | MultiStrOpt | `['cinder.api.contrib.standard_extensions']` | 决定扩展/Action 是否挂载 | `cinder/common/config.py:104-106` |
| `osapi_volume_ext_list` | ListOpt | `[]` | 配合 `select_extensions` 使用 | `cinder/common/config.py:99-103` |
| `auth_strategy` | StrOpt | `keystone` | 枚举 `noauth\|keystone` | `cinder/common/config.py:165-169` |
| `service_down_time` | IntOpt | `60` | 服务存活判定秒数 | `cinder/common/config.py:155-158` |
| `storage_availability_zone` | StrOpt | `nova` | 可被后端 `backend_availability_zone` 覆盖 | `cinder/common/config.py:122-126` |
| `default_availability_zone` | StrOpt | 无（未设） | 未设时取 `storage_availability_zone` | `cinder/common/config.py:127-130` |
| `allow_availability_zone_fallback` | BoolOpt | `False` | 允许可用区回退 | `cinder/common/config.py:131-136` |
| `default_volume_type` / `default_group_type` | StrOpt | 无（未设） | — | `cinder/common/config.py:137-140` |
| `volume_usage_audit_period` | StrOpt | `month` | 枚举 `hour\|day\|month\|year` | `cinder/common/config.py:141-144` |
| `rootwrap_config` | StrOpt | `/etc/cinder/rootwrap.conf` | 指向 rootwrap 过滤器配置 | `cinder/common/config.py:145-148` |
| `monkey_patch` / `monkey_patch_modules` | BoolOpt / ListOpt | `False` / `[]` | — | `cinder/common/config.py:149-154` |
| `volume_manager` | StrOpt | `cinder.volume.manager.VolumeManager` | — | `cinder/common/config.py:107-109` |
| `backup_manager` | StrOpt | `cinder.backup.manager.BackupManager` | — | `cinder/common/config.py:110-112` |
| `scheduler_manager` | StrOpt | `cinder.scheduler.manager.SchedulerManager` | — | `cinder/common/config.py:113-115` |
| `fatal_exception_format_errors` | BoolOpt | `False` | 异常格式化失败是否致命 | `cinder/exception.py:40-47` |
| `glance_api_version` | IntOpt | `2` | 已标弃用（Queens 移除 v1） | `cinder/common/config.py:56-61` |
| `glance_num_retries` | IntOpt | `0`（min=0） | — | `cinder/common/config.py:62-65` |
| `glance_api_insecure` / `glance_api_ssl_compression` | BoolOpt | `False` / `False` | — | `cinder/common/config.py:66-77` |

完整配置项注册表由 `cinder/opts.py:212-229` (`list_opts`) 以 `(组名, opts)` 元组暴露给 `oslo.config.opts`（`setup.cfg:44-45`），生成配置见 `tools/config/cinder-config-generator.conf`（[构建与测试手册](../operations/dev-and-test.md) 的 `genconfig`）。

### 3.2 Glance / Swift / Key Manager 配置

| 配置域 | 配置键 | 默认值 | 说明 | 源码锚点 |
|---|---|---|---|---|
| Glance | `allowed_direct_url_schemes` | `[]` | 允许 `file`/`cinder` 方案 | `cinder/image/glance.py:42-47` |
| Glance | `glance_catalog_info` | `image:glance:publicURL` | 未配 `glance_api_servers` 时使用 | `cinder/image/glance.py:48-53` |
| Glance | `glance_core_properties` | `['checksum','container_format','disk_format','image_name','image_id','min_disk','min_ram','name','size']` | 镜像核心属性 | `cinder/image/glance.py:55-64` |
| Swift Backup | `swift_catalog_info` | `object-store:swift:publicURL` | 未设 URL 时按目录发现 | `cinder/backup/drivers/swift.py:67-72` |
| Swift Backup | `keystone_catalog_info` | `identity:Identity Service:publicURL` | 未设 auth URL 时使用 | `cinder/backup/drivers/swift.py:73-78` |
| Swift Backup | `backup_swift_auth` | `per_user`（枚举 `per_user\|single_user`） | 认证方式 | `cinder/backup/drivers/swift.py:79-82` |
| Swift Backup | `backup_swift_auth_version` | `1` | 支持 `1`/`2`/`3` | `cinder/backup/drivers/swift.py:83-86` |
| Swift Backup | `backup_swift_container` | `volumebackups` | 默认容器 | `cinder/backup/drivers/swift.py:107-109` |
| Swift Backup | `backup_swift_object_size` | `52428800` | 对象字节数 | `cinder/backup/drivers/swift.py:110-112` |
| Swift Backup | `backup_swift_block_size` | `32768` | 增量块字节数，须整除 object_size | `cinder/backup/drivers/swift.py:113-117` |
| Swift Backup | `backup_swift_retry_attempts` | `3` | 重试次数 | `cinder/backup/drivers/swift.py:118-120` |
| Swift Backup | `backup_swift_retry_backoff` | `2` | 退避秒数 | `cinder/backup/drivers/swift.py:121-123` |
| Swift Backup | `backup_swift_enable_progress_timer` | `True` | 进度通知定时器 | `cinder/backup/drivers/swift.py:124-129` |
| Swift Backup | `backup_swift_auth_insecure` | `False` | 跳过证书校验 | `cinder/backup/drivers/swift.py:133-136` |
| Swift Backup | `backup_swift_key` | 无（未设），`secret=True` | 认证密钥，不明文回显 | `cinder/backup/drivers/swift.py:104-106` |
| `key_manager` 组 | `fixed_key` | 无（未设），旧组名 `keymgr` | 固定密钥（十六进制） | `cinder/keymgr/conf_key_mgr.py:45-52` |

## 4. 中间件默认头与配置来源

`set_middleware_defaults`（`cinder/common/config.py:222-247`）在进程启动时覆盖 oslo.middleware CORS 默认值：`allow_headers` 含 `X-Auth-Token`、`X-Identity-Status`、`X-Roles`、`X-OpenStack-Request-ID`、`OpenStack-API-Version` 等；`expose_headers` 含 `X-Subject-Token`、`X-Service-Token`；`allow_methods` 为 `GET/PUT/POST/DELETE/PATCH/HEAD`。该函数同时注册为 `oslo.config.opts.defaults` 入口（`setup.cfg:46-47`），由 `cinder/cmd/api.py:52` 与 `cinder/wsgi/wsgi.py:43` 调用。

## 5. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 新增全局配置项 | `cinder/common/config.py:47-219`、`cinder/opts.py:212-408` | 只 `register_opts` 而不加入 `list_opts` 会导致 `oslo-config-generator` 生成的样例缺失该项；弃用项需填写 `deprecated_for_removal`/`deprecated_reason` |
| 改 Swift 块大小 | `cinder/backup/drivers/swift.py:110-117`、`148-156` | `backup_swift_object_size` 必须是 `backup_swift_block_size` 的整数倍，否则增量备份偏移错乱 |
| 改 KEY/密钥配置 | `cinder/keymgr/conf_key_mgr.py:45-52`、`cinder/backup/drivers/swift.py:104-106`、`cinder/service.py:647-659` | 含 `_password`/`_key` 的键在 `service.wait` 日志中被脱敏为 `FLAG SET`；新秘密选项须沿用 `secret=True` 或该脱敏规则 |
| 改后端组回退 | `cinder/volume/configuration.py:74-135`、`etc/cinder/api-paste.ini:5-75` | 后端组默认值被改写为 `None` 以判定显式设置，改这里会影响所有 volume driver 的取值 |
| 改驱动 `LANG` 写入 | `cinder/volume/drivers/hitachi/vsp_utils.py:576`、`cinder/volume/drivers/hitachi/hbsd_fc.py:60`、`cinder/volume/drivers/hitachi/hbsd_iscsi.py:68` | 三处写入需一致；移除会导致命令输出解析随宿主 locale 漂移 |
| 改扩展默认加载 | `cinder/common/config.py:104-106`、`cinder/api/contrib/*.py` | `osapi_volume_extension` 默认值决定哪些 Action 生效，详见 [扩展 Action 全集](api/extensions.md) |

接口侧的鉴权开关与状态码见 [入向接口总表](api-reference.md) 与 [错误码字典](error-codes.md)。
