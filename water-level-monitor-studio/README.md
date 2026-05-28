# Water Level Monitor Studio

Python 桌面端水位监测控制台，用于对接现有 `water-level-monitor` 后端，也支持离线演示模式。

## 功能

- PySide6 桌面端主界面
- JWT 登录现有 Spring Boot 后端
- 实时监控工作台
- 监控大屏，汇总设备、报警、趋势和风险态势
- 设备列表、在线状态、阈值统计和设备详情查看
- 历史水位查询与 CSV / Excel / JSON 导出
- 报警中心支持设备筛选、类型筛选、报警统计、单条处理和一键处理
- 报警处理闭环，记录处理人、备注和待同步动作，支持离线恢复后补同步
- 数据分析中心，包含统计指标、移动平均、趋势斜率和异常点检测
- AI 智能分析中心，自动生成运维报告、硬件联调建议，并支持 PDF / TXT 导出
- 硬件联调工具，可模拟 ESP32 上传 JSON、预览请求体、随机生成报文、字段校验并保留上传记录
- 虚拟 ESP32 自动上传模拟器，支持定时上传、曲线模式和异常尖峰
- SQLite 本地缓存，接口异常时可降级查看缓存数据
- 数据库维护中心，支持表记录统计、旧数据清理和 SQLite 压缩
- 登录角色控制，支持管理员、调试员和访客三类权限
- SockJS/STOMP 实时推送订阅，接收 `/topic/water-level`、`/topic/device-status`、`/topic/alarm`
- 系统日志支持级别筛选、统计、清空和 CSV 导出
- 系统自检支持环境检查、缓存备份、缓存恢复和自检报告导出
- 配置中心可查看后端地址、缓存文件、运行模式、最近同步状态，并支持生成演示数据、切换模式和导出快照

## 运行

```bash
cd /Users/zhujifan/water-level-monitor-studio
source .venv/bin/activate
python run.py
```

也可以使用启动器自动检查依赖和代码编译：

```bash
python launcher.py
```

默认连接：

```text
后端地址：http://localhost:8080
账号：admin
密码：请在 .env 中配置 WLM_DEFAULT_PASSWORD，或在登录窗口手动输入
```

如果后端没有运行，可以在登录窗口勾选“离线演示模式”。

## 页面模块

```text
实时监控：当前水位、阈值、状态和趋势曲线
监控大屏：设备、报警、趋势和风险汇总展示
设备管理：设备编号、位置、在线状态、阈值和最近上报时间
历史数据：按设备和时间范围查询，支持 CSV / Excel / JSON 导出
报警中心：设备筛选、类型筛选、报警统计、单条处理和一键处理
数据分析：统计指标、移动平均和趋势曲线
AI 智能分析：自动生成运维报告，提供硬件联调问答
硬件联调：模拟 ESP32 上传 deviceCode/waterLevel/rawValue/warningLevel/dangerLevel，展示协议预览和上传记录
虚拟 ESP32：按曲线模式自动生成水位并模拟定时上传
系统日志：记录接口、缓存、导出和推送事件，支持级别筛选和 CSV 导出
数据库维护：查看缓存体积、表记录数，执行清理和压缩
系统自检：检查 Python 环境、缓存、设备、后端、实时推送和待同步任务
配置中心：查看运行模式、缓存路径、同步状态，并支持生成演示数据、模式切换和快照导出
```

## 配置

可以复制 `.env.example` 为 `.env` 后修改：

```bash
cp .env.example .env
```

主要配置项：

```text
WLM_API_BASE_URL=http://localhost:8080
WLM_DEFAULT_USERNAME=admin
WLM_DEFAULT_PASSWORD=your_password_here
WLM_CACHE_PATH=data/studio_cache.sqlite3
WLM_REQUEST_TIMEOUT=5
```

## 检查

```bash
./scripts/check.sh
./scripts/test.sh
```

## 打包

使用 PyInstaller 打包：

```bash
./scripts/build_app.sh
```

## 简历亮点

```text
基于 PySide6 开发工业监控类桌面客户端，对接 Spring Boot 物联网后端；
通过 REST + SockJS/STOMP 实现数据查询与实时水位推送；
使用 SQLite 实现本地缓存和接口异常降级；
使用 pyqtgraph 实现实时趋势曲线，openpyxl/reportlab 实现报表导出；
引入 AI 智能分析模块，基于水位记录、报警数据和设备阈值生成运维建议；
提供硬件联调工作台，可验证 ESP32 上传协议、设备编号、阈值和报警链路；
提供虚拟 ESP32 自动上传、监控大屏、角色权限、系统自检、缓存备份恢复和数据快照导出，增强项目交付能力。
```
