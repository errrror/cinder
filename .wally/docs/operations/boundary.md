---
kind: operations
scope: boundary
status: draft
origin: generated
source_paths: []
symbols: []
upstream: [INDEX.md]
downstream: [architecture/index.md]
---

# 认知边界与外部黑盒声明（Agent Anti-Hallucination Boundary）

本页界定本套 `.wally/docs/` 已核验的源码快照、仓库外不可见的黑盒系统、静态分析的局限与外部权威页的归属，防止 Agent 把弱命中当字面证据或脑补仓外实现。

## 1. 核验基准快照与生成物状态

- **Git 分支与提交**：`chore/wally-init-20261124-c11` @ `7cfb472b9baf7e5bc8364f4d6a7380f55a2668d1`。
- **生成模式与覆盖目录**：`FULL`（无有效 `.wiki-meta.json` 基线，工作树干净）。已完整扫描并建档：`cinder/api/`、`cinder/backup/`、`cinder/brick/`、`cinder/cmd/`、`cinder/common/`、`cinder/compute/`、`cinder/consistencygroup/`、`cinder/db/`、`cinder/group/`、`cinder/hacking/`、`cinder/image/`、`cinder/interface/`、`cinder/keymgr/`、`cinder/locale/`、`cinder/message/`、`cinder/objects/`、`cinder/scheduler/`、`cinder/tests/`、`cinder/transfer/`、`cinder/volume/`、`cinder/wsgi/`、`cinder/zonemanager/`、`api-ref/`、`contrib/`、`doc/`、`etc/`、`rally-jobs/`、`releasenotes/`、`tools/`、`.wally/`。
- **生成物可信度声明**：除显式标为 `origin: human` / `status: verified` 的人工精修页外，所有页面均为 `status: draft` / `origin: generated`；Agent 改动核心逻辑前必须按页内 `路径:行号` 回读源码字面核验。

## 2. 仓库外黑盒系统清单（Out-of-Repo Black Boxes）

以下目标仅在本仓库内存在出向调用封装，其服务端内部实现不在本仓库内（请求/响应字典按本仓代码记录，远端内部逻辑严禁猜测）：

| 外部黑盒目标 | 本仓边界文件（`路径:行号`） | 本仓已核实的契约范围 | 不可见的远端黑盒范围 |
|---|---|---|---|
| `Glance` 镜像服务 | `cinder/image/glance.py:147-217` | glanceclient 方法名、重试异常集合、镜像属性键集合 | 服务端存储后端、真实限流阈值、服务目录实际地址 |
| `Nova` 计算服务 | `cinder/compute/nova.py:107-249` | 认证参数、事件字典 `name/server_uuid/tag`、方法签名 | 虚机侧事件消费逻辑、调度与配额配置 |
| `Swift / Ceph / NFS / POSIX / TSM / Google` 备份后端 | `cinder/backup/drivers/swift.py:144-393`、`cinder/backup/driver.py:348` | Connection 参数、对象命名前缀、返回 etag 校验 | 远端对象环、副本策略、认证服务内部状态 |
| `oslo.messaging` 传输（RabbitMQ 等） | `cinder/rpc.py:55-70,141-159` | Topic、cast/call、序列化器与版本门禁 | Broker 集群拓扑、镜像队列策略、实际投递延迟 |
| `Barbican / Key Manager` | `cinder/keymgr/conf_key_mgr.py:57-146` | 密钥接口方法、`fixed_key` 配置型回退 | 外部 KMS 实现与审计策略 |
| `FC Fabric` 交换机 | `cinder/zonemanager/utils.py:30-121` | `conn_info` 键 `driver_volume_type`/`data/initiator_target_map` | 交换机 zoning 表、VSAN 拓扑 |
| 存储阵列与 `os-brick` | `cinder/volume/driver.py:2114-2464`、`cinder/interface/util.py:42-60` | 驱动接口方法与 `connection_info` 结构 | 阵列内部卷布局、固件行为、真实健康检查阈值 |
| Keystone 认证中间件 | `etc/cinder/api-paste.ini:71-75` | 管线顺序、注入的 `cinder.context` | token 签发与吊销状态 |

## 3. 动态分发与运行期注入边界

| 动态机制位置（`路径:行号`） | 机制说明 | Agent 注意事项 |
|---|---|---|
| `cinder/interface/util.py:42-60` | 按 cinder.conf 中的驱动字符串运行时 `import` 类 | 静态分析无法穷举实际驱动；改接口需按厂商逐一验证 |
| `etc/cinder/api-paste.ini:5-75` | PasteDeploy 按 `auth_strategy` 选择 noauth/keystone 管线 | 部署态管线与仓库默认值可能不同，排障时先确认实际配置 |
| `cinder/coordination.py:67-119` | coordination 后端由配置决定（文件/etcd/Redis 等） | 锁语义依赖外部后端，单测无法覆盖真实竞争 |
| `cinder/cmd/volume.py:84-108` | `enabled_backends` 决定启动哪些多后端进程 | 未列出的后端不会被加载，改配置后需重启进程 |
| `cinder/policy.py:31-73` | 运行期加载 `policy.json`，权限不是编译期常量 | 新增 action 必须同步 `etc/cinder/policy.json` |
| `cinder/service.py:647-659` | 日志按配置键名脱敏，但敏感值来自运行期文件 | 不要把真实凭据写进单测 fixture 或文档示例 |

## 4. 外部权威页与 SOP 专用页归属（不纳入 codewiki 管理页）

下列文件由 wally-init / SOP 流程维护，属于外部权威引用页：**不强制 8 键 YAML 头、不复制正文、不自动改写为 codewiki 模板**，仅在本套文档中链接引用；G1 的 `pageOrder` / `pageCount` 不计入这些页。

| 外部页 | 用途 | 排除理由 |
|---|---|---|
| `.wally/docs/apis/index.md`、`.wally/docs/apis/_template.md` | SOP API 契约索引与模板（尚为骨架） | SOP 专用模板，正文由任务流程填充，非本 skill 生成物 |
| `.wally/docs/sqls/README.md` | 数据库与 SQL 文档骨架 | SOP 专用模板；真实表结构由 [领域模型](../business/domain-models/index.md) 覆盖 |
| `.wally/docs/unittest/unittest.md` | 单测策略规范 | SOP 专用权威页；可执行命令见 [构建与单测](dev-and-test.md) |
| `.wally/docs/integration_test/integration_test.md` | 集成测试规范与 readiness 记录 | SOP 专用，`readiness: pending` 需人工补齐，禁止自动改写 |
| `.wally/docs/devops/env.md` | 开发环境骨架 | SOP 专用模板 |
| `.wally/docs/devops/test-env-deploy.md` | 测试环境部署静态核验记录 | SOP 专用，`readiness: pending`，与 [部署与运行时](deployment-and-runtime.md) 互补而非重复 |

## 5. 共变耦合与修改清单（Co-Change Playbook）

1. 新增仓库外下游系统：只在本页第 2 节与 [集成总览](../integrations/index.md) 第 3 节登记边界，不写远端内部实现；契约页只展开本仓发出的字典键。
2. 快照推进：只有工作树干净且 G1–G5 全绿时才把 `.wiki-meta.json` 的 `commitHash` 推进到当前 HEAD；含未提交源码时保留旧基线并记录检查的 HEAD。
3. 发现外部权威页被本 skill 覆盖：立即从 Git 恢复该文件内容，并在验收报告中记为人工页保护事件。
