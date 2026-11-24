# Integration testing

> 静态核验：仅读取仓库文件，未执行测试。对象：cinder（基线 master）。

## 真实入口与来源

- `tox.ini` `[testenv:functional]`：`OS_TEST_PATH=./cinder/tests/functional`，底层命令 `ostestr`；入口 `tox -e functional`。
- `setup.cfg` 声明 `tempest.test_plugins = cinder_tests = cinder.tests.tempest.plugin:CinderTempestPlugin`，插件代码 `cinder/tests/tempest/plugin.py` 把 `cinder/tests/tempest` 注册到 Tempest；仓库内无 `tempest run` 命令。
- `test-requirements.txt` 含 `tempest>=16.1.0`、`os-testr`；`tox.ini` 另有 `compliance`、`fast8`、`cover` 等环境。

## 前置条件

- 完整 IT（Tempest）需要已部署的 OpenStack 环境及其认证配置（tempest.conf / openrc / credential），仓库内未提供这些内容。

## 缺口与判据

- `tox -e functional` 为仓库内 functional 测试，不等同于对已部署环境的端到端 IT。
- 未定义集成测试目标环境、认证/配置获取方式、数据准备与隔离、通过标准、失败分类、清理与证据位置。
- 因此 `it.readiness = pending`、`success_criteria` 暂缺；执行前须补齐，不得猜测命令或声称通过。
