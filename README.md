# Smart Water Level Monitoring System

完整的水位监测物联网系统，包含 ESP32 硬件采集端、PySide6 桌面监控控制台和 MATLAB 离线分析脚本。系统支持水位采集、阈值报警、数据上传、实时推送、历史查询、报警处理、离线缓存、硬件联调和数据分析。

## 系统架构

```text
ESP32 + HC-SR04 + ST7789 + 蜂鸣器
        |
        | HTTP JSON 上传水位、原始值和阈值
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

## 项目亮点

- ESP32 端使用 HC-SR04 超声波传感器采集水位，开机自动校准容器高度并动态计算预警/危险阈值。
- 硬件端实现 7 次中值滤波、EMA 指数平滑、低水位噪声过滤和显示防抖，提高采样稳定性。
- ESP32 通过 WiFi 每 5 秒向后端上传 JSON 数据，包含设备编号、水位、原始测量值、预警阈值和危险阈值。
- ST7789 TFT 彩屏展示设备编号、水位、距离、状态、上传结果、WiFi 状态和运行时长，并通过蜂鸣器实现两级本地报警。
- PySide6 桌面端支持实时监控、监控大屏、设备管理、历史数据、报警中心、数据分析、AI 智能分析、硬件联调和虚拟 ESP32。
- SQLite 本地缓存支持接口异常时离线查看设备、水位、报警和日志数据。
- SockJS/STOMP 实时推送支持水位、设备状态和报警消息订阅。
- MATLAB 脚本支持从本地 CSV 或后端导出接口读取数据，生成水位曲线、移动平均、直方图、趋势拟合和报警分布图。

## 技术栈

Python、PySide6、SQLite、Requests、WebSocket、STOMP/SockJS、pyqtgraph、openpyxl、reportlab、PyInstaller、ESP32、Arduino C++、HC-SR04、ST7789 TFT、MATLAB

## 启动命令速查

首次安装桌面端：

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

后端未启动时，可以在登录窗口勾选“离线演示模式”。

## 目录结构

```text
esp32/water_level_sensor/       ESP32 采集端程序
matlab/water_level_analysis.m   MATLAB 离线分析脚本
water-level-monitor-studio/     PySide6 桌面端
```

## 桌面端运行

```bash
cd water-level-monitor-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

默认连接后端：

```text
http://localhost:8080
```

如果后端未运行，可以在登录窗口勾选“离线演示模式”。

## ESP32 端配置

打开：

```text
esp32/water_level_sensor/water_level_sensor.ino
```

按你的本地环境修改：

```cpp
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL = "http://YOUR_SERVER_IP:8080/api/water-level/upload";
const char* DEVICE_CODE = "WL-004";
```

依赖 Arduino 库：

- ArduinoJson v6
- TFT_eSPI
- ESP32 开发板支持包

`chinese_bmp.h` 用于 TFT 屏幕中文位图显示，需要与 `.ino` 文件放在同一目录。

## MATLAB 分析

方式一：将后端导出的 `water_level_data.csv` 放到 `matlab/` 目录后运行脚本。

方式二：通过环境变量配置后端连接信息，由脚本自动登录并下载 CSV：

```bash
export WLM_API_BASE_URL=http://localhost:8080
export WLM_USERNAME=your_username
export WLM_PASSWORD=your_password
```

然后在 MATLAB 中运行：

```matlab
water_level_analysis
```

## 测试

```bash
cd water-level-monitor-studio
python -m unittest discover -s tests -p "test_*.py"
```
