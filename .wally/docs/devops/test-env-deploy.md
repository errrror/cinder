# Test environment deployment

> 静态核验：仅读取仓库文件，未执行构建/部署/测试。对象：cinder（基线 master）。

## 真实入口与来源

- `contrib/block-box/README.md`、`contrib/block-box/Makefile`、`contrib/block-box/docker-compose.yml`：可选的容器化 Cinder demo（block-box），使用 noauth。
- 构建/启动（工作目录 `contrib/block-box`）：`make`（构建 cinder / cinder-lvm / cinder-devenv 三个镜像），`docker-compose up -d`（启动 mariadb、rabbitmq、cinder-api、cinder-scheduler、cinder-volume）。
- 服务可执行文件（`setup.cfg` console_scripts）：`cinder-api`、`cinder-scheduler`、`cinder-volume`、`cinder-backup`；compose 中分别以 `sh /init-scripts/cinder-api.sh`、`cinder-scheduler`、`cinder-volume` 启动，依赖 mariadb/rabbitmq。
- 客户端配置：`contrib/block-box/cinder.rc` 提供 noauth 示例变量（OS_AUTH_TYPE=noauth、CINDER_ENDPOINT=http://127.0.0.1:8776/v3、OS_PROJECT_ID、OS_USERNAME、OS_VOLUME_API_VERSION=3.27）。

## 前置条件与配置

- Docker / docker-compose；可访问镜像构建源（openstack/loci-cinder 等）；使用 LVM 后端时需先在宿主机准备 `etc-cinder/cinder.conf` 指定的 volume group。
- 配置集中在 `contrib/block-box/etc-cinder/cinder.conf`；数据库与消息队列由 compose 提供；示例密码为 `password`，不得用于生产。

## 验证与回滚（缺口）

- `cd contrib/block-box && docker-compose ps` 查看容器状态；README 给出 cinderclient `list` 的调用示例（需另行准备客户端容器）。
- 仓库内未定义正式回滚命令、触发条件与数据清理步骤，无有效版本核对与健康检查验收判据。
- 未指定目标测试环境标识/负责人/授权边界，未提供正式凭证获取方式。因此 `deploy.readiness = pending`；执行前须补齐，不得猜测命令。
