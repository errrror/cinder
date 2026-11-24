---
kind: operations
scope: dev-and-test
status: draft
origin: generated
source_paths: [setup.cfg, tox.ini, requirements.txt, test-requirements.txt, cinder/test.py, cinder/tests/unit/api/v3/test_volumes.py, cinder/tests/unit/api/contrib/test_volume_actions.py, cinder/tests/unit/test_exception.py, cinder/tests/unit/test_service.py, cinder/tests/tempest/plugin.py]
symbols: [main, ostestr, set_middleware_defaults, VolumeApiTest.setUp, VolumeActionsTest.setUp, CinderTempestPlugin.load_tests]
upstream: [INDEX.md, contracts/api-reference.md]
downstream: [operations/deployment-and-runtime.md, operations/pitfalls-and-adr.md]
---

# 构建、启动与单测验证手册（Agent Verification Playbook）

本页给出从依赖安装到精准回归的可执行命令，全部来自 `tox.ini`、`setup.cfg`、`requirements.txt` 与测试源码。Cinder 是 Python 单仓项目（Python 2.7 / 3.5，见 `tox.ini:4`），无前端构建步骤。验证闭环：先装约束依赖 → 跑对应模块单测 → 跑 pep8/静态检查 → 必要时跑 functional/compliance。配置项的生成方式见 [配置项全集](../contracts/configuration.md)，进程拓扑见 [部署与运行期](deployment-and-runtime.md)。

## 1. 环境前置与可执行命令速查

| 动作 | 精确执行命令 | 配置来源（`路径:行号`） | 备注 / 前置约束 |
|---|---|---|---|
| 安装依赖 | `pip install -c{env:UPPER_CONSTRAINTS_FILE:https://git.openstack.org/cgit/openstack/requirements/plain/upper-constraints.txt} {opts} {packages}` | `tox.ini:13` | tox 自动执行；如需覆盖设 `UPPER_CONSTRAINTS_FILE` |
| 运行依赖清单 | `requirements.txt` | `requirements.txt:1-40` | `pbr>=2.0.0`、`eventlet<0.21.0`、`oslo.*` 系列、`PasteDeploy>=1.5.0` 等 |
| 测试依赖清单 | `test-requirements.txt` | `test-requirements.txt:1-25` | `hacking<0.14`、`mock>=2.0.0`、`oslotest>=1.10.0`、`ostestr>=0.8.0`、`tempest>=16.1.0`、`bandit>=1.1.0` |
| 默认全量单测 | `tox`（envlist=`py35,py27,compliance,pep8`） | `tox.ini:4`、`tox.ini:21-23` | 命令体为 `find . -name "*.pyc" -delete` + `ostestr {posargs}` |
| 指定解释器/并发 | `tox -epy27 -- --concurrency=4` | `tox.ini:17-23` | 默认并发为 CPU 核数 |
| 精准单测（类名/用例名） | `tox -epy35 -- VolumeApiTest` 或 `ostestr cinder.tests.unit.api.v3.test_volumes` | `tox.ini:21-23`、`cinder/tests/unit/api/v3/test_volumes.py:46` | `{posargs}` 直接透传给 ostestr 作过滤表达式 |
| functional 测试 | `tox -efunctional`（`OS_TEST_PATH=./cinder/tests/functional`） | `tox.ini:42-44` | 需要 DB/RabbitMQ 等外部依赖 |
| compliance 测试 | `tox -ecompliance`（`OS_TEST_PATH=./cinder/tests/compliance`） | `tox.ini:52-54` | 校验驱动契约 |
| 静态检查 / Lint | `tox -epep8`：`flake8 .` + `tools/config/check_uptodate.sh` + `tools/check_exec.py` | `tox.ini:56-60` | flake8 忽略 `E251`，启用 `H106,H203,H904`，`max-complexity=30`（`tox.ini:126-135`） |
| 快速静态检查 | `tox -efast8` → `tools/fast8.sh` | `tox.ini:62-66` | 复用 pep8 环境目录 |
| 覆盖率 | `tox -ecover` → `python setup.py testr --coverage` + `coverage report` | `tox.ini:73-79` | 排除 `test.*coverage` 用例 |
| 配置样例生成 | `tox -egenconfig` → `oslo-config-generator --config-file=tools/config/cinder-config-generator.conf` | `tox.ini:81-84` | 改配置注册后必须跑 |
| 选项文档生成 | `tox -egenopts` → `python tools/config/generate_cinder_opts.py` | `tox.ini:86-89` | 与 `cinder/opts.py:212` 联动 |
| 安全静态扫描 | `tox -ebandit` → `bandit -r cinder -n5 -x tests -ll` | `tox.ini:107-109` | 排除 tests 目录 |
| 系统依赖探测 | `tox -ebindep` → `bindep test` | `tox.ini:115-124` | 不安装依赖，仅报告缺失 |
| 文档构建 | `tox -edocs`、`tox -eapi-ref`、`tox -ereleasenotes` | `tox.ini:30-40`、`tox.ini:94-100` | Sphinx/doc8 校验 |
| 启动 API 服务 | `cinder-api`（`cinder.cmd.api:main`） | `setup.cfg:49`、`cinder/cmd/api.py:47-63` | 先 `rpc.init(CONF)`，再 `service.WSGIService('osapi_volume')` 启动 |
| 启动其余服务 | `cinder-scheduler` / `cinder-volume` / `cinder-backup` / `cinder-volume-usage-audit` | `setup.cfg:50-56` | 各自 console_scripts 入口 |
| 冒烟自检 | `GET /` 返回全版本清单（HTTP 300） | `cinder/api/versions.py:131-136` | 期望 `_KNOWN_VERSIONS` 完整 JSON |
| 管理命令 | `cinder-manage --help` 列出 11 类子命令 | `setup.cfg:51`、`cinder/cmd/manage.py:699-749` | 类别由 `CATEGORIES` 反射生成 |

## 2. 源码模块 → 必跑回归测试映射表

| 被修改的源码文件 / 目录 | 必跑测试文件 | 关键测试函数 / 覆盖契约点 | 精确运行命令 |
|---|---|---|---|
| `cinder/api/v3/volumes.py` | `cinder/tests/unit/api/v3/test_volumes.py` | `VolumeApiTest.test_check_volume_filters_called` (:56)、`test_volume_index_filter_by_glance_metadata` (:116)、`test_volume_index_filter_by_group_id` (:139) | `tox -epy35 -- VolumeApiTest` |
| `cinder/api/v3/attachments.py` | `cinder/tests/unit/api/v3/test_attachments.py` | 附件创建/更新/完成契约 | `tox -epy35 -- cinder.tests.unit.api.v3.test_attachments` |
| `cinder/api/v3/backups.py` | `cinder/tests/unit/api/v3/test_backups.py` | 备份字段与微版本 | `tox -epy35 -- cinder.tests.unit.api.v3.test_backups` |
| `cinder/api/v3/groups.py`、`group_snapshots.py` | `cinder/tests/unit/api/v3/test_groups.py`、`test_group_snapshots.py` | 组创建/复制动作 | `tox -epy35 -- cinder.tests.unit.api.v3.test_groups` |
| `cinder/api/contrib/volume_actions.py` | `cinder/tests/unit/api/contrib/test_volume_actions.py` | `VolumeActionsTest.test_initialize_connection` (:100)、`test_terminate_connection` (:162)、`test_simple_api_actions` (:89) | `tox -epy35 -- VolumeActionsTest` |
| `cinder/api/contrib/admin_actions.py` | `cinder/tests/unit/api/contrib/test_admin_actions.py` | 强制删除/迁移/状态重置 | `tox -epy35 -- cinder.tests.unit.api.contrib.test_admin_actions` |
| `cinder/exception.py` | `cinder/tests/unit/test_exception.py` | `CinderExceptionTestCase.test_default_error_msg` (:42)、`test_error_msg` (:49) | `tox -epy35 -- CinderExceptionTestCase` |
| `cinder/service.py` | `cinder/tests/unit/test_service.py:70-97` | `ServiceManagerTestCase.test_message_gets_to_manager` (:75)、`test_reset` (:97) | `tox -epy35 -- ServiceManagerTestCase` |
| `cinder/common/config.py`、`cinder/opts.py` | `tox -egenconfig` + `tox -egenopts`（`tools/config/check_uptodate.sh`） | 配置注册与样例一致性 | `tox -epep8` |
| 任意 volume driver（`cinder/volume/drivers/`） | `tox -ecompliance` | 驱动接口契约（`cinder/tests/compliance/`） | `tox -ecompliance` |
| 跨服务端到端 | `cinder/tests/tempest/plugin.py:22-38` | `CinderTempestPlugin.load_tests` 返回 `cinder/tests/tempest` 目录，注册 `volume_feature_group` | `tox -efunctional` 后由 tempest 发现 |

## 3. 测试环境隔离与 Mock / Fixture 编写规范

从 `cinder/test.py`、`cinder/tests/unit/api/contrib/test_volume_actions.py` 提取的硬约定（新增单测必须复用）：

1. **全局 Fixture 隔离**：`cinder/test.py:128-152` 的 `setUp` 依次挂 `fixtures.Timeout`（受 `OS_TEST_TIMEOUT` 控制）、`fixtures.NestedTempfile`、`fixtures.TempHomeDir`、`log_fixture.get_logging_handle_error_fixture()`；需要捕获输出时用 `fixtures.MonkeyPatch('sys.stdout'/'sys.stderr', ...)`（`:145-150`）。
2. **RPC 后端隔离**：`self.flags(rpc_backend='cinder.openstack.common.rpc.impl_fake')`（`cinder/tests/unit/api/contrib/test_volume_actions.py:87`），禁止单测直连真实消息总线。
3. **API 方法打桩 + 清理**：对每个外部调用用 `mock.patch 目标为 cinder.volume.api.API 下的具体方法名`，`start()` 后必须 `self.addCleanup(patcher.stop)` 并设 `return_value`（`cinder/tests/unit/api/contrib/test_volume_actions.py:60-85`）。
4. **DB 层打桩**：`mock.patch('cinder.db.sqlalchemy.api._volume_get')` 隔离数据库（`cinder/tests/unit/api/contrib/test_volume_actions.py:81-85`）。
5. **WSGI 上下文注入**：用 `fakes.wsgi_app(fake_auth_context=self.context)` 构造请求，避免真实鉴权（`cinder/tests/unit/api/contrib/test_volume_actions.py:89-92`）。
6. **提交禁令**：禁止把 `*.pyc`（`tox.ini:22` 主动删除）、测试临时库、日志或本机会话记录提交；`requirements.txt`/`test-requirements.txt` 的排序注释（`requirements.txt:1-4`）要求新增依赖写明许可证与顺序理由。

## 4. 共变耦合与修改清单

| 变更点 | 联动文件 | 隐式陷阱与标准动作 |
|---|---|---|
| 改配置注册 | `cinder/common/config.py`、`cinder/opts.py:212`、`tox.ini:81-89` | 必须重跑 `tox -egenconfig`/`-egenopts`，`tox -epep8` 的 `check_uptodate.sh` 会校验样例是否过期 |
| 改 API 过滤/字段 | `cinder/api/v3/volumes.py`、`cinder/tests/unit/api/v3/test_volumes.py:56-151` | 过滤键与微版本分支须补对应单测；`resource_filters.json` 也需同步（见 [接口参数字典](../contracts/api/v3-volumes.md)） |
| 改 Action 实现 | `cinder/api/contrib/volume_actions.py`、`cinder/tests/unit/api/contrib/test_volume_actions.py:54-92` | 新增打桩方法必须加入 `self.api_patchers` 并 `addCleanup`，否则测试间状态泄漏 |
| 改异常码 | `cinder/exception.py`、`cinder/tests/unit/test_exception.py:27-53` | 状态码变化需同步 [错误码字典](../contracts/error-codes.md) 与控制器内即时翻译 |
| 改入口脚本 | `setup.cfg:48-58`、`cinder/cmd/manage.py:699-749` | console_scripts 与 `cinder-manage` 的 `CATEGORIES` 两处独立，漏一处即不可执行 |

更多运行期约束见 [部署、进程拓扑与持久化目录契约](deployment-and-runtime.md)；历史死代码与改动雷区见 [高危雷区与存量死代码](pitfalls-and-adr.md)。
