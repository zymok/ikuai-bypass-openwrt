# 源码与构建

## 目录

```text
package/           LuCI、配置辅助、服务、WhatsApp、订阅保护及 YAML 依赖
tests/             单元测试与真实核心的本机模拟接口测试
scripts/           固定版本核心下载与校验
vendor/            上游核心来源清单和对应源码归档
docs/              使用文档
build.py           IPK 打包入口
LICENSE            AGPL-3.0
NOTICE.md          原作者、修改范围及第三方许可
```

`downloads/` 和 `dist/` 是本机构建产物，不进入源码版本控制。源码和发布包均不需要现场密码。

## 构建 OpenWrt 包装版

需要 Python 3.10+；打包脚本本身只使用标准库，无需 OpenWrt SDK。它打包经过 SHA-256 校验的官方核心，不重新编译 Rust。

```sh
python3 scripts/fetch-core.py
python3 build.py
```

产物位于 `dist/`，包含 `.ipk` 与 `.ipk.sha256`。只打包 x86_64。tar/gzip 的生成时间会影响整个 IPK 的字节校验值，重新打包不保证与已发布 IPK 字节一致；核心文件按清单固定校验。

## 上游对应源码

原作者为 [joyanhui](https://github.com/joyanhui)，原项目 [ikuai-bypass](https://github.com/joyanhui/ikuai-bypass)。核心固定为 `ikuai-bypass-v4.4.110`，提交 `aba8d1ccf57194e7e33f5967a7a6cf9b61e01f89`。下载地址和 SHA-256 见 `vendor/UPSTREAM.json`。

`vendor/ikuai-bypass-v4.4.110-source.tar.gz` 从该提交归档生成，包含 Rust workspace、CLI/core/GUI/测试应用源码、前端、锁文件、构建脚本、CI、许可证及配置；不包含与本 CLI 构建无关的旧 Go 二进制、路由器虚拟机磁盘和演示图片。完整原项目也可以直接按固定 tag 获取：

```sh
git clone --branch ikuai-bypass-v4.4.110 --depth 1 https://github.com/joyanhui/ikuai-bypass.git
cd ikuai-bypass
```

如需自行编译核心，按上游工具链安装 Rust（支持 edition 2024）、Bun，以及目标平台链接器。先构建前端资源，再构建 CLI：

```sh
cd frontends/app
bun install --frozen-lockfile
bun run build
cd ../..
cargo build --locked --release --target x86_64-unknown-linux-musl -p ikb-cli
```

目标和系统库准备以归档中的上游 CI 为准。本项目当前发布的是官方核心，以上源码编译路径未在本次包装发布中完整复验。不要将 Windows/glibc 二进制直接用于 OpenWrt，也不要绕过清单校验替换后继续宣称使用官方固定核心。

## 测试

测试需要 PyYAML，可在隔离虚拟环境安装，或将已包含的纯 Python YAML 依赖加入路径：

```sh
PYTHONPATH=package/vendor python3 -m unittest discover -s tests -v
```

WhatsApp 事务测试依赖 Linux 的 `fcntl/flock`，Windows 会跳过。真实核心保护测试在已安装本包的 Linux/OpenWrt 执行：

```sh
python3 tests/core_download_failure_probe.py --guard
python3 tests/core_download_failure_probe.py --guard --cron
```

模拟服务器和下载地址均为 `127.0.0.1`，临时配置不指向现网爱快；不会拿生产规则做清空测试。缺少受保护包装器时不能把测试“没运行起来”误当作通过。

## 重新发布

更新 `build.py` 的修订号和 `CHANGELOG.md`，在隔离环境完成测试、确认默认密码为空，再构建 IPK。Release 同时附上 IPK、SHA-256 和对应源码归档，保留原作者和所有许可证。不要上传路由器配置、附加功能状态、现场日志或备份。
