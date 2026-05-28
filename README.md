# Smart Water Level Monitoring System

完整的水位监测物联网系统，包含 ESP32 硬件采集端、PySide6 桌面监控控制台和 MATLAB 离线分析脚本。系统覆盖“现场采集、阈值报警、数据上传、实时推送、桌面监控、离线缓存、硬件联调、数据分析”的完整闭环。

## 项目定位

这个项目适合用于展示物联网应用、桌面软件、传感器数据处理和工程化联调能力。项目不仅包含桌面端界面，还包含硬件采集程序和离线分析脚本，能够说明完整链路设计能力：

```text
传感器采集 -> ESP32 本地处理 -> HTTP 上传 -> 后端入库/推送 -> 桌面端监控 -> MATLAB 离线分析
```

## 系统架构

```text
ESP32 + HC-SR04 + ST7789 + 蜂鸣器
        |
        | HTTP JSON 上传水位、原始值、预警阈值、危险阈值
        v
Spring Boot 后端接口
        |
        | REST 查询 + SockJS/STOMP 实时推送
        v
PySide6 桌面监控控制台
        |
        | CSV 导出 / API 下载
        v
MATLAB 离线统计分析与可视化
```

## 核心功能

| 模块 | 功能说明 |
| --- | --- |
| ESP32 采集端 | 使用 HC-SR04 超声波传感器测距，基于容器高度换算水位 |
| 自动校准 | 开机空容器校准容器高度，并动态计算预警阈值和危险阈值 |
| 数据滤波 | 使用 7 次中值滤波、EMA 指数平滑、低水位噪声过滤和显示防抖 |
| 本地显示 | 使用 ST7789 TFT 展示设备编号、水位、距离、状态、上传结果、WiFi 状态和运行时长 |
| 本地报警 | 使用蜂鸣器实现预警短响和危险急促连响 |
| 数据上传 | 每 5 秒通过 WiFi 向后端 `/api/water-level/upload` 上传 JSON 数据 |
| 桌面控制台 | 基于 PySide6 实现实时监控、监控大屏、设备管理、历史数据、报警中心、数据分析、AI 分析、硬件联调等模块 |
| 离线缓存 | 使用 SQLite 缓存设备、水位、报警、日志和待同步动作，支持后端异常时降级查看 |
| 实时推送 | 通过 SockJS/STOMP 订阅水位、设备状态和报警消息 |
| 虚拟 ESP32 | 支持定时生成水位曲线、异常尖峰和模拟上传，便于无硬件演示 |
| MATLAB 分析 | 从 CSV 或后端导出接口读取数据，生成曲线、移动平均、直方图、趋势拟合和报警分布 |

## 技术栈

- 桌面端：Python、PySide6、pyqtgraph、Requests、websocket-client、stomp.py
- 本地缓存：SQLite
- 导出能力：CSV、Excel、PDF、openpyxl、reportlab
- 硬件端：ESP32、Arduino C++、HC-SR04、ST7789 TFT、TFT_eSPI、ArduinoJson
- 实时通信：SockJS、STOMP、WebSocket
- 离线分析：MATLAB
- 打包：PyInstaller

## 数据流

```text
HC-SR04 测距
    |
    v
中值滤波 + EMA 平滑 + 噪声过滤
    |
    v
水位 = 容器高度 - 传感器到水面的距离
    |
    +--------------------+
    |                    |
    v                    v
TFT 显示 / 蜂鸣器报警     HTTP JSON 上传后端
                         |
                         v
                后端状态判断 / 报警记录 / WebSocket 推送
                         |
                         v
                PySide6 桌面端实时刷新
```

## 目录结构

```text
esp32/water_level_sensor/
  water_level_sensor.ino       ESP32 主程序
  chinese_bmp.h                TFT 中文位图资源

matlab/
  water_level_analysis.m       水位数据离线分析脚本

water-level-monitor-studio/
  app/api_client.py            后端 REST API 客户端
  app/ws_client.py             SockJS/STOMP 实时推送客户端
  app/cache.py                 SQLite 本地缓存
  app/ai.py                    规则型运维分析和问答
  app/simulator.py             离线演示数据生成
  app/ui/                      PySide6 页面、组件、样式和图标
  scripts/                     运行、检查、测试、打包脚本
  tests/                       核心逻辑测试
```

## 桌面端启动命令

首次安装：

```bash
cd water-level-monitor-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动桌面端：

```bash
cd water-level-monitor-studio
source .venv/bin/activate
python run.py
```

也可以使用脚本：

```bash
cd water-level-monitor-studio
./scripts/run.sh
```

默认后端地址：

```text
http://localhost:8080
```

后端未启动时，可以在登录窗口勾选“离线演示模式”。

## 桌面端配置

复制配置模板：

```bash
cd water-level-monitor-studio
cp .env.example .env
```

配置示例：

```env
WLM_API_BASE_URL=http://localhost:8080
WLM_DEFAULT_USERNAME=admin
WLM_DEFAULT_PASSWORD=your_password_here
WLM_CACHE_PATH=data/studio_cache.sqlite3
WLM_REQUEST_TIMEOUT=5
```

真实 `.env` 不应提交到仓库。

## ESP32 端配置

打开：

```text
esp32/water_level_sensor/water_level_sensor.ino
```

按本地网络环境修改：

```cpp
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL = "http://YOUR_SERVER_IP:8080/api/water-level/upload";
const char* DEVICE_CODE = "WL-004";
```

注意：

- ESP32 与后端服务器需要在同一局域网。
- `SERVER_URL` 不能写 `localhost`，因为对 ESP32 来说 localhost 指的是设备自身。
- `DEVICE_CODE` 需要与后端设备表中的设备编号一致。
- 烧录前需要安装 ESP32 开发板支持包、ArduinoJson v6 和 TFT_eSPI。
- `chinese_bmp.h` 需要与 `.ino` 文件放在同一目录。

## MATLAB 分析

方式一：将后端导出的 `water_level_data.csv` 放到 `matlab/` 目录，然后运行：

```matlab
water_level_analysis
```

方式二：通过环境变量配置后端连接信息，由脚本自动登录并下载 CSV：

```bash
export WLM_API_BASE_URL=http://localhost:8080
export WLM_USERNAME=your_username
export WLM_PASSWORD=your_password
```

脚本会输出：

- 水位变化曲线
- 移动平均平滑曲线
- 水位分布直方图
- 线性趋势拟合图
- 正常/预警/危险占比图
- `analysis_results.txt` 文本结果

## 测试与检查

启动前检查：

```bash
cd water-level-monitor-studio
./scripts/check.sh
```

运行测试：

```bash
cd water-level-monitor-studio
./scripts/test.sh
```

手动测试：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

测试覆盖：

- 模拟设备和历史水位生成
- 报警生成逻辑
- 统计摘要和风险分析
- SQLite 缓存写入、查询、清理和压缩

## 打包

```bash
cd water-level-monitor-studio
./scripts/build_app.sh
```

打包输出会生成到 `dist/`，该目录属于构建产物，不提交到 Git。

## 安全与仓库说明

- 真实 WiFi 名称、WiFi 密码、后端账号密码和 `.env` 不应提交到仓库。
- SQLite 缓存、导出文件、打包产物和截图产物均已加入 `.gitignore`。
- 公开仓库中的 ESP32 配置使用占位符，烧录前需要改成本地真实配置。
- MATLAB 下载的 CSV 数据默认不纳入版本控制，避免提交真实运行数据。

## 简历描述参考

设计并实现水位监测物联网系统，包含 ESP32 硬件采集端、PySide6 桌面监控控制台和 MATLAB 离线分析脚本；硬件端基于 HC-SR04 实现水位采集、滤波平滑、动态阈值和本地报警，桌面端通过 REST + SockJS/STOMP 对接后端，实现实时监控、设备管理、报警处理、历史查询、离线缓存、硬件联调和数据导出。
