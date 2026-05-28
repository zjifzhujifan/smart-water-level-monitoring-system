/*
 * ====================================================================
 *  ESP32 水位监测系统 v3.0
 * ====================================================================
 *
 * 【系统简介】
 *   本系统基于 ESP32 微控制器，使用 HC-SR04 超声波传感器测量水位，
 *   通过 WiFi 将数据上传至 Spring Boot 后端服务器，并在本地 TFT 屏幕
 *   实时显示水位信息。当水位超过预设阈值时，蜂鸣器发出本地报警。
 *
 * 【程序定位】
 *   本文件是硬件端主程序，承担“数据源”的角色。它不负责用户登录、
 *   历史查询、报警处理等后台管理功能，而是专注于以下四件事：
 *   1. 从超声波传感器读取距离；
 *   2. 根据容器高度计算当前水位；
 *   3. 将水位、阈值和原始测量值上传给后端；
 *   4. 在设备本地完成屏幕展示和蜂鸣器提示。
 *
 * 【运行状态机】
 *   设备运行过程可以理解为一个简单状态机：
 *
 *     上电启动
 *        ↓
 *     硬件初始化
 *        ↓
 *     空容器校准  ← 通过多次测距得到 containerHeight
 *        ↓
 *     阈值计算    ← warnLevel = 60%, alarmLevel = 80%
 *        ↓
 *     WiFi连接
 *        ↓
 *     周期运行
 *        ├─ 每5秒采集、滤波、计算水位、上传后端
 *        ├─ 每次采集后根据阈值执行本地蜂鸣器报警
 *        └─ 每1秒刷新屏幕运行时长
 *
 *   其中“周期运行”会一直持续，除非设备断电或复位。
 *
 * 【硬件清单】
 *   1. ESP32 开发板 (主控芯片，内置WiFi+蓝牙)
 *   2. HC-SR04 超声波测距传感器 (测量范围: 2cm~400cm，精度: ±3mm)
 *   3. 1.54寸 ST7789 TFT 彩色显示屏 (分辨率: 240x240，SPI接口)
 *   4. 有源蜂鸣器 (3.3V驱动，HIGH电平触发)
 *
 * 【硬件接线表】
 *   ┌────────────────┬──────────┬───────────────────────────┐
 *   │ 模块           │ 引脚     │ ESP32 GPIO                │
 *   ├────────────────┼──────────┼───────────────────────────┤
 *   │ HC-SR04        │ TRIG     │ GPIO 5  (输出-发送脉冲)   │
 *   │                │ ECHO     │ GPIO 19 (输入-接收回波)   │
 *   │                │ VCC      │ 5V                        │
 *   │                │ GND      │ GND                       │
 *   ├────────────────┼──────────┼───────────────────────────┤
 *   │ 蜂鸣器         │ I/O      │ GPIO 4  (HIGH=响)         │
 *   │                │ VCC      │ 3.3V                      │
 *   │                │ GND      │ GND                       │
 *   ├────────────────┼──────────┼───────────────────────────┤
 *   │ ST7789 TFT     │ SDA/MOSI │ 在TFT_eSPI库配置文件中设置│
 *   │                │ SCL/SCLK │ (User_Setup.h)            │
 *   │                │ CS/DC/RST│                           │
 *   └────────────────┴──────────┴───────────────────────────┘
 *
 * 【测量原理】
 *   超声波传感器安装在容器顶部，向下发射声波并接收水面反射的回波。
 *   通过测量声波往返时间，计算传感器到水面的距离：
 *
 *     传感器 ───────── (安装在容器顶部)
 *        │  ↓↑ 超声波
 *        │  距离(distance)
 *        ↓
 *     ～～水面～～     ← 水位(waterLevel) = 容器高度 - 距离
 *        │
 *        │  水位
 *        ↓
 *     ─────────────── (容器底部)
 *
 *   距离公式: distance = 声波往返时间(us) × 声速(0.0343 cm/us) ÷ 2
 *   水位公式: waterLevel = containerHeight - distance
 *
 * 【数据处理流水线】
 *   原始测量 → 中值滤波(7次采样取中值) → EMA指数平滑(α=0.15) → 噪声过滤 → 最终水位
 *
 *   1. 中值滤波: 连续采集7次，排序后取中间值，消除偶发异常值(如飞溅水花干扰)
 *   2. EMA平滑: 新值 = 旧值×0.85 + 测量值×0.15，抑制连续测量间的高频噪声
 *   3. 噪声过滤: 水位 < 1.0cm 归零，消除空容器时的微小测量波动
 *   4. 显示防抖: 水位变化 < 0.3cm 不刷新屏幕，避免数字频繁跳动
 *
 * 【报警分级机制】
 *   系统采用两级报警，阈值基于校准时测得的容器高度动态计算：
 *   - 正常状态: 水位 < 预警阈值(60%)           → 不报警
 *   - 预警状态: 预警阈值(60%) ≤ 水位 < 危险阈值(80%) → 蜂鸣器短响1次
 *   - 危险状态: 水位 ≥ 危险阈值(80%)            → 蜂鸣器急促连响5次
 *
 * 【与服务端的协作】
 *   - 每5秒通过HTTP POST上传一次JSON数据到后端 /api/water-level/upload 接口
 *   - 上传内容包含: 设备编号、水位值、原始值、预警阈值、危险阈值
 *   - 后端收到数据后会:
 *     a) 将阈值与数据库比对，不同则更新（实现硬件→Web端阈值同步）
 *     b) 根据阈值判断水位状态(0正常/1预警/2危险)并入库
 *     c) 通过WebSocket推送实时数据到前端Dashboard
 *     d) 超阈值时自动创建报警记录
 *   - 后端每15秒检查一次设备心跳，若超过30秒未收到数据则判定设备离线
 *
 * 【上传字段与后端字段对应关系】
 *   ESP32上传JSON字段        后端DTO字段                 数据库/业务含义
 *   ---------------------------------------------------------------------------
 *   deviceCode             WaterLevelUploadDTO.deviceCode  设备编号，关联device表
 *   waterLevel             WaterLevelUploadDTO.waterLevel  当前水位，单位cm
 *   rawValue               WaterLevelUploadDTO.rawValue    原始测量值，便于排查
 *   warningLevel           WaterLevelUploadDTO.warningLevel 预警阈值，单位cm
 *   dangerLevel            WaterLevelUploadDTO.dangerLevel  危险阈值，单位cm
 *
 * 【状态码对应关系】
 *   后端会根据本程序上传的 waterLevel、warningLevel、dangerLevel 重新判断状态：
 *   0 = 正常，1 = 预警，2 = 危险。
 *   设备端本地蜂鸣器报警与后端状态判断使用同一套阈值，因此现场提示和平台展示一致。
 *
 * 【异常处理策略】
 *   - 测距失败：单次测距返回 -1，中值滤波阶段会丢弃无效值；
 *   - 连续失败：若7次测距全部失败，沿用上一轮 smoothDistance，避免水位突然跳变；
 *   - WiFi断开：本地采集、显示和蜂鸣器仍继续工作，上传返回失败；
 *   - 上传失败：屏幕显示“失败”，后端会因长时间未收到数据将设备判定为离线；
 *   - 后端不可达：不会影响本地报警，但前端实时监控和历史记录会缺失对应数据。
 */

#include <WiFi.h>          // ESP32 WiFi库，用于无线网络连接
#include <HTTPClient.h>    // HTTP客户端库，用于向服务器发送POST请求
#include <ArduinoJson.h>   // JSON序列化库(v6)，用于构造上传数据的JSON格式
#include <TFT_eSPI.h>      // TFT屏幕驱动库（需在User_Setup.h中配置SPI引脚映射）
#include <SPI.h>           // SPI通信库（TFT屏幕通信协议，硬件SPI）
#include "chinese_bmp.h"   // 自定义中文字符位图头文件（预渲染的中文像素数据，用于在TFT上显示中文）

// ==================== 网络与设备配置 ====================
// WiFi热点名称和密码（需要与本地路由器/热点匹配）。
// 上传到公开仓库前不要写入真实 WiFi 名称和密码；烧录到设备前在本地替换为真实值。
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// 后端服务器数据上传接口地址
// 注意: IP地址需要与后端服务器在同一局域网，端口默认8080
// 对应后端 WaterLevelController.java 的 @PostMapping("/upload") 接口
// 如果后端运行在电脑本机，YOUR_SERVER_IP 应替换为电脑在当前局域网中的IPv4地址，
// 不能填写 localhost，因为对ESP32来说 localhost 指的是ESP32自己，不是电脑。
const char* SERVER_URL = "http://YOUR_SERVER_IP:8080/api/water-level/upload";

// 当前设备编号，必须与后端数据库 device 表中的 device_code 字段一致
// 后端通过此编号识别设备身份（DeviceService.getByCode()）
// 如果后端 device 表中没有 WL-004，上传接口会返回错误，数据不会入库。
const char* DEVICE_CODE = "WL-004";

// ==================== 硬件引脚定义 ====================
// HC-SR04 超声波传感器引脚
const int TRIG_PIN   = 5;   // GPIO5 - 触发引脚(OUTPUT): 向传感器发送10us高电平脉冲，触发超声波发射
const int ECHO_PIN   = 19;  // GPIO19 - 回波引脚(INPUT): 接收传感器返回的回波信号，高电平持续时间=声波往返时间
// 蜂鸣器引脚
const int BUZZER_PIN = 4;   // GPIO4 - 蜂鸣器控制(OUTPUT): HIGH=发声，LOW=静音

// ==================== 报警阈值百分比 ====================
// 基于容器高度的百分比动态计算，在 setup() 校准完成后自动确定具体值(cm)
// 例如: 容器高度=25cm → 危险阈值=20cm, 预警阈值=15cm
const float ALARM_PERCENT = 0.80;  // 危险阈值 = 容器高度 × 80%（水位达到此值表示即将溢出）
const float WARN_PERCENT  = 0.60;  // 预警阈值 = 容器高度 × 60%（水位达到此值需要关注）

// ==================== 数据稳定性参数 ====================
// 这些参数经过实际调试优化，在测量精度和响应速度之间取得平衡
//
// NOISE_THRESHOLD (噪声阈值):
//   空容器时传感器仍可能读到微小波动(如温度变化导致的声速偏差)，
//   低于此值的水位直接归零，避免显示"0.1cm""0.2cm"等无意义数据。
//   也可以理解为“最小有效水位”：只有水位达到 1cm 以上，才认为是真实水位变化。
const float NOISE_THRESHOLD = 1.0;   // 单位: cm
//
// CHANGE_THRESHOLD (显示防抖阈值):
//   水面微小波纹会导致测量值在 ±0.1~0.3cm 范围内抖动，
//   只有变化量超过此值才刷新屏幕，防止数字频繁闪烁影响阅读。
const float CHANGE_THRESHOLD = 0.3;  // 单位: cm
//
// EMA_ALPHA (指数移动平均系数):
//   EMA公式: smoothed = previous × (1 - α) + current × α
//   α越小 → 平滑效果越强，但对真实变化的响应越慢
//   α越大 → 响应越快，但噪声抑制效果越弱
//   0.15 是经验值，对5秒采集间隔表现良好
const float EMA_ALPHA = 0.15;

// ==================== 上传间隔 ====================
// 每隔 UPLOAD_INTERVAL 毫秒执行一次数据采集和上传
// 该值需与后端设备健康检查配合:
//   后端 DeviceHealthService 每15秒检查一次，30秒无数据则判定离线
//   因此上传间隔必须 < 30秒，5秒是一个安全且不会过于频繁的值
const int UPLOAD_INTERVAL = 5000;    // 单位: 毫秒 (5秒)

// ==================== 全局变量 ====================
TFT_eSPI tft = TFT_eSPI();           // TFT屏幕驱动对象实例（SPI通信）

// ---- 时间控制变量 ----
unsigned long lastUploadTime = 0;     // 上次数据采集+上传的时间戳(ms)，用于控制5秒间隔
unsigned long lastUptimeUpdate = 0;   // 上次刷新运行时长显示的时间戳(ms)，用于控制1秒间隔
unsigned long bootTime = 0;           // 系统启动时间戳(ms)，由 millis() 赋值；后续用 millis()-bootTime 计算已运行多久

// ---- 测量与校准变量 ----
float containerHeight = 0;            // 容器高度(cm)，即传感器到容器底部的距离；开机空容器校准得到，是水位换算基准
float alarmLevel = 0;                 // 危险水位阈值(cm) = containerHeight × ALARM_PERCENT(0.80)
float warnLevel = 0;                  // 预警水位阈值(cm) = containerHeight × WARN_PERCENT(0.60)
float smoothDistance = -1;            // EMA平滑后的传感器到水面距离(cm)，-1表示尚未初始化（首次测量时直接赋值）
float lastDisplayLevel = -999;        // 上次屏幕显示的水位值(cm)，用于防抖判断（初始值-999确保首次一定刷新）

// ---- 上传统计变量 ----
int uploadCount = 0;                  // 累计上传尝试次数（含成功和失败），显示在屏幕底部
int uploadFailCount = 0;              // 累计上传失败次数，用于评估网络稳定性；当前未直接显示，可通过串口或后续扩展展示

// ==================== 屏幕颜色定义 (RGB565格式) ====================
// RGB565编码: 红色5位(bit15~11) + 绿色6位(bit10~5) + 蓝色5位(bit4~0) = 16位/像素
// 这是TFT屏幕常用的颜色编码格式，每个像素占2字节
#define COLOR_BG       0x0000  // 纯黑色 (R:0  G:0  B:0)  - 屏幕背景色
#define COLOR_TITLE    0x07FF  // 青色   (R:0  G:63 B:31) - 标题文字、设备编号
#define COLOR_NORMAL   0x07E0  // 纯绿色 (R:0  G:63 B:0)  - 正常状态指示
#define COLOR_WARN     0xFFE0  // 纯黄色 (R:31 G:63 B:0)  - 预警状态指示
#define COLOR_ALARM    0xF800  // 纯红色 (R:31 G:0  B:0)  - 危险/报警状态指示
#define COLOR_TEXT     0xFFFF  // 纯白色 (R:31 G:63 B:31) - 普通文字内容
#define COLOR_GRAY     0x7BEF  // 中灰色 - 标签文字(如"水位""距离""状态")
#define COLOR_DARKGRAY 0x4208  // 深灰色 - 次要信息、分隔线、底部栏文字
#define COLOR_BLUE     0x001F  // 纯蓝色 (R:0  G:0  B:31) - 备用颜色
#define COLOR_CYAN     0x07FF  // 青色   - 进度条填充、装饰元素(与TITLE同色)
#define COLOR_BAR_BG   0x2104  // 极深灰 - 进度条未填充部分的背景色

// ==================================================================================
//                              setup() 系统初始化函数
// ==================================================================================
// 系统上电后仅执行一次，完成以下初始化流程:
//   1. 硬件初始化: 串口、引脚模式、蜂鸣器、TFT屏幕
//   2. 开机画面: 显示设备编号、水滴图标、校准提示
//   3. 自动校准: 空容器状态下测量10次取中值，得到容器高度，自动计算报警阈值
//   4. WiFi连接: 尝试连接指定热点，最多等待15秒
//   5. 绘制主界面: 构建正常工作时的屏幕静态框架
//
// 重要说明:
//   校准阶段会把“传感器到容器底部的距离”作为容器高度。
//   因此设备开机时容器应尽量保持空桶状态，如果桶内已有水，设备会把水面当成桶底，
//   导致 containerHeight 偏小，进而影响后续水位值和阈值计算。
void setup() {
  Serial.begin(115200);   // 初始化串口通信，波特率115200bps，用于调试信息输出
  bootTime = millis();    // millis()返回开机到当前经过的毫秒数；这里把“启动时刻”保存下来，后续用于计算运行时长

  // ---- 引脚模式配置 ----
  pinMode(TRIG_PIN, OUTPUT);     // HC-SR04触发引脚: 设为输出模式，用于发送10us脉冲
  pinMode(ECHO_PIN, INPUT);      // HC-SR04回波引脚: 设为输入模式，用于读取回波高电平时长
  pinMode(BUZZER_PIN, OUTPUT);   // 蜂鸣器引脚: 设为输出模式，HIGH触发发声
  digitalWrite(BUZZER_PIN, LOW); // 确保蜂鸣器初始处于关闭状态，避免上电时误响

  // 开机提示音: 短响1次(200ms)，告知用户系统已启动
  buzzerBeep(1, 200, 100);

  // ---- TFT屏幕初始化 ----
  tft.init();              // 初始化ST7789屏幕驱动芯片
  tft.setRotation(0);     // 设置屏幕方向: 0=竖屏(240宽×240高)，1=横屏，2/3=旋转180°/270°
  tft.fillScreen(COLOR_BG); // 全屏填充黑色背景，清除上电时的随机像素

  // ======== 开机画面显示 ========
  // 在屏幕中央显示设备标识信息和校准提示，持续约2秒
  tft.setTextDatum(MC_DATUM);  // 设置文字对齐方式: MC_DATUM = Middle Center (水平垂直居中)
  tft.setTextColor(COLOR_TITLE, COLOR_BG);  // 前景色=青色, 背景色=黑色(覆盖写入，避免残影)
  tft.drawString("WL-004", 120, 50, 4);  // 在坐标(120,50)处显示设备编号，字体大小4

  // 绘制装饰性水滴图标（由圆形+三角形组合而成）
  tft.fillCircle(120, 100, 12, COLOR_CYAN);              // 水滴下半部分: 圆心(120,100) 半径12
  tft.fillTriangle(108, 96, 132, 96, 120, 76, COLOR_CYAN); // 水滴上半部分: 等腰三角形，顶点朝上

  // 显示"水位 Monitor"文字标签
  tft.setTextColor(COLOR_GRAY, COLOR_BG);
  drawShuiWei(tft, 84, 125, COLOR_GRAY);  // 调用位图函数绘制中文"水位"（TFT_eSPI不原生支持中文）
  tft.drawString("Monitor", 148, 133, 2); // 英文部分直接使用库函数，字体大小2

  // 显示校准操作提示信息
  tft.setTextColor(COLOR_WARN, COLOR_BG);
  tft.drawString("Calibrating...", 120, 165, 2);  // 黄色提示"正在校准..."
  tft.setTextColor(COLOR_DARKGRAY, COLOR_BG);
  tft.drawString("Keep container EMPTY", 120, 190, 1);  // 灰色提示"请保持容器为空"

  // 绘制校准进度条外框 (位置x:40, y:210, 宽160, 高10)
  tft.drawRect(40, 210, 160, 10, COLOR_GRAY);

  Serial.println("=== WL-004 正在校准 ===");

  delay(1000);  // 等待1秒让传感器供电稳定，避免刚上电时的不稳定读数

  // ======== 开机自动校准过程 ========
  // 【目的】测量传感器到容器底部的距离，作为"容器高度"基准
  // 【前提】校准时容器必须处于空/无水状态，否则会把水面误认为容器底部
  // 【方法】连续测量10次，过滤无效值后对有效值取中值(中值比均值更抗异常值干扰)
  // 【业务意义】该高度会决定后续所有水位计算和报警阈值，是设备端最关键的基准值。
  float readings[10];  // 存储有效测量值的数组
  int count = 0;       // 有效测量值计数器
  for (int i = 0; i < 10; i++) {
    float d = singleMeasure();  // 执行一次超声波测距
    // 有效性过滤: HC-SR04量程为2~400cm，超出此范围的视为无效测量
    if (d > 0 && d < 400) { readings[count++] = d; }
    // 更新屏幕上的校准进度条动画
    int pw = (int)((i + 1) / 10.0 * 156);  // 计算进度条当前应填充的像素宽度(最大156px)
    tft.fillRect(42, 212, pw, 6, COLOR_CYAN);  // 从左向右逐步填充青色
    delay(150);  // 每次测量间隔150ms，给传感器余振衰减的时间
  }

  // 计算容器高度: 取有效值的中值(排序后取中间位置的值)
  // containerHeight 表示“传感器到容器底部的距离”，不是当前水位。
  // 后续当前水位通过 levelCm = containerHeight - smoothDistance 计算。
  if (count == 0) containerHeight = 20.0;  // 所有测量均无效时，使用20cm作为安全默认值，避免后续除零或阈值为0
  else { sortArray(readings, count); containerHeight = readings[count / 2]; } // 有有效读数时先排序，再取中间值作为容器高度

  // 根据容器高度动态计算两级报警阈值
  // 例: 容器高度=25cm → alarmLevel=20cm(80%), warnLevel=15cm(60%)
  // 这些阈值会通过 uploadData() 上传到后端，实现“设备端校准结果 → 平台端阈值配置”的同步。
  alarmLevel = containerHeight * ALARM_PERCENT;  // 危险阈值: 水位超过此值触发危险报警
  warnLevel  = containerHeight * WARN_PERCENT;   // 预警阈值: 水位超过此值触发预警提醒
  smoothDistance = containerHeight;  // 初始化EMA平滑值: 空容器时距离=容器高度(传感器到底部)

  Serial.printf("校准完成 → 容器高:%.1fcm 预警线:%.1fcm 危险线:%.1fcm\n", containerHeight, warnLevel, alarmLevel);

  // ---- 校准完成，在屏幕上显示校准结果 ----
  tft.fillRect(0, 155, 240, 70, COLOR_BG);  // 用黑色覆盖清除之前的校准提示文字
  tft.setTextColor(COLOR_NORMAL, COLOR_BG);  // 绿色表示校准成功
  tft.setTextDatum(MC_DATUM);
  char calBuf[32];
  sprintf(calBuf, "%.1f cm", containerHeight);
  tft.drawString(calBuf, 120, 170, 4);  // 大字体显示校准得到的容器高度
  tft.drawString("OK!", 120, 200, 2);    // 显示"OK!"表示校准完成

  // 校准完成提示音: 快速短响2次，与开机的1次区分
  buzzerBeep(2, 100, 100);
  delay(1000);  // 展示校准结果1秒

  // ---- 连接WiFi网络 ----
  connectWiFi();  // 尝试连接WiFi，最多等待15秒
  delay(500);     // 连接成功后等待500ms让网络协议栈稳定

  // ---- 绘制正常工作时的主界面 ----
  drawUI();  // 绘制静态UI框架（标题栏、标签、进度条框、分隔线等）
}

// ==================================================================================
//                              loop() 主循环函数
// ==================================================================================
// Arduino框架下 loop() 会被无限循环调用，每次执行完自动重新进入。
// 本函数负责两个定时任务:
//   1. 每5秒 (UPLOAD_INTERVAL): WiFi检查 → 数据采集 → 滤波处理 → 屏幕刷新 → 报警判断 → 上传
//   2. 每1秒: 刷新屏幕上的运行时长显示 (HH:MM:SS)
//
// 本程序没有使用 delay() 写一个固定死循环来采集，而是使用 millis() 做时间片调度。
// 好处是采集上传和运行时长刷新互不阻塞，后续如果增加按键、更多传感器或更多显示项也更容易扩展。
void loop() {
  // ---- WiFi断线自动重连 ----
  // 每次循环都检查WiFi状态，断线时立即尝试重连
  // 重连期间不阻塞数据采集和屏幕显示，只是上传会失败
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  unsigned long now = millis();  // 获取当前运行毫秒数；它是相对开机时间，不是现实年月日时间

  // ==================== 定时数据采集与上传（每5秒一次）====================
  if (now - lastUploadTime >= UPLOAD_INTERVAL) {
    lastUploadTime = now;  // 更新时间戳，开始下一个5秒计时周期

    // ---- 步骤1: 中值滤波测距 ----
    // measureDistance() 内部执行7次单次测量，排序后取中值
    // 中值滤波的优势: 即使7次中有1~2次异常值(如水花飞溅、电磁干扰)，
    // 中间值仍然是可靠的，比平均值更抗离群点干扰
    float rawDist = measureDistance();

    // ---- 步骤2: EMA指数移动平均平滑 ----
    // 公式: smoothed(t) = smoothed(t-1) × (1 - α) + measured(t) × α
    // 其中 α = EMA_ALPHA = 0.15
    //   → 新测量值权重15%，历史累积值权重85%
    //   → 相当于约 1/α ≈ 6.7 次采样的移动平均效果
    //   → 有效抑制连续测量间的高频噪声波动
    // 注意: smoothDistance 在 setup() 中已初始化为 containerHeight
    smoothDistance = smoothDistance * (1.0 - EMA_ALPHA) + rawDist * EMA_ALPHA;

    // ---- 步骤3: 计算水位 ----
    // 传感器安装在容器顶部，测量的是到水面的距离
    // 水位 = 容器总高度 - 传感器到水面的距离
    // 水越多 → 距离越短 → 水位越高
    float levelCm = containerHeight - smoothDistance;

    // ---- 步骤4: 边界保护与噪声过滤 ----
    // 低值过滤: 水位低于 NOISE_THRESHOLD(1cm) 归零
    //   原因: 空容器时传感器噪声可能导致计算出0.1~0.5cm的"假水位"
    //   NOISE_THRESHOLD 的作用就是把这些小抖动当成噪声，不参与显示、报警和上传判断。
    if (levelCm < NOISE_THRESHOLD) levelCm = 0;
    // 高值限幅: 水位不能超过容器高度
    //   原因: 测量误差可能导致 smoothDistance < 0，此时 levelCm > containerHeight
    if (levelCm > containerHeight) levelCm = containerHeight;

    // 计算传感器原始值(raw value): 平滑距离 × 10 取整
    // 上传给后端用于记录原始传感器数据，便于后续数据分析和问题排查
    int rawValue = (int)(smoothDistance * 10);

    // 计算水位百分比: 用于屏幕进度条和垂直水位条的显示
    // 防除零: 如果 containerHeight 为0(极端异常情况)，百分比设为0
    float percent = (containerHeight > 0) ? (levelCm / containerHeight * 100.0) : 0;

    // 串口输出调试信息: 便于通过 Serial Monitor 实时查看数据处理各阶段的值
    Serial.printf("原始距离:%.2fcm → 平滑距离:%.2fcm → 水位:%.2fcm (%.0f%%)\n",
                  rawDist, smoothDistance, levelCm, percent);

    // ---- 步骤5: 屏幕显示防抖 ----
    // 只有满足以下任一条件才刷新屏幕:
    //   a) 水位变化量 ≥ CHANGE_THRESHOLD(0.3cm) — 有明显变化
    //   b) lastDisplayLevel < -900 — 首次显示(初始值为-999)
    // 目的: 避免水面微小波动导致屏幕数字频繁跳动，提升可读性
    if (abs(levelCm - lastDisplayLevel) >= CHANGE_THRESHOLD || lastDisplayLevel < -900) {
      lastDisplayLevel = levelCm;  // 记录本次显示值，作为下次防抖的基准
      updateDisplay(levelCm, smoothDistance, percent);  // 刷新屏幕动态内容
    }

    // ---- 步骤6: 本地蜂鸣器报警检查 ----
    // 根据当前水位与预警/危险阈值的关系，触发不同级别的蜂鸣器报警
    // 注意: 这是本地报警(蜂鸣器)，与后端报警记录(AlarmService)是独立的两套机制
    checkAlarm(levelCm);

    // ---- 步骤7: 通过HTTP将数据上传到后端服务器 ----
    // 上传放在本地显示和蜂鸣器报警之后：
    //   即使网络异常，现场人员仍能先看到屏幕数据并听到蜂鸣器报警；
    //   网络恢复后，设备会继续上传新数据，后端再更新在线状态。
    uploadCount++;  // 累计上传尝试次数
    bool success = uploadData(rawValue, levelCm);  // 执行HTTP POST上传
    if (!success) uploadFailCount++;  // 记录失败次数
    updateUploadStatus(success);  // 在屏幕上显示本次上传结果("成功"/"失败")
  }

  // ==================== 每秒刷新运行时长显示 ====================
  // 独立于数据采集周期，每秒更新一次屏幕上的 HH:MM:SS 运行时长
  if (now - lastUptimeUpdate >= 1000) {
    lastUptimeUpdate = now;
    updateUptime();  // 刷新运行时长文字
  }
}

// ==================== buzzerBeep() 蜂鸣器控制函数 ====================
// 控制有源蜂鸣器发出指定次数和节奏的提示音
//
// 参数:
//   times - 响声次数 (例: 1=单次提示, 2=双响确认, 5=急促报警)
//   onMs  - 每次响声持续时间(毫秒) (例: 80=急促短响, 200=正常提示)
//   offMs - 两次响声之间的静音间隔(毫秒) (最后一次响声后不加间隔)
//
// 使用示例:
//   buzzerBeep(1, 200, 100)  → 开机提示: 响200ms
//   buzzerBeep(2, 100, 100)  → 校准完成: 嘀嘀两声
//   buzzerBeep(5, 80, 80)    → 危险报警: 急促连响5次
//   buzzerBeep(1, 150, 0)    → 预警提醒: 短响一声
void buzzerBeep(int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH);  // 拉高引脚 → 蜂鸣器发声
    delay(onMs);                     // 保持发声指定时长
    digitalWrite(BUZZER_PIN, LOW);   // 拉低引脚 → 蜂鸣器静音
    if (i < times - 1) delay(offMs); // 非最后一次时，添加间隔静音期
  }
}

// ==================== singleMeasure() 单次超声波测距 ====================
// 执行一次完整的超声波测距操作，是所有测距功能的基础函数。
//
// 【工作原理】
//   1. 向 TRIG_PIN 发送一个 ≥10us 的高电平脉冲
//   2. HC-SR04 收到触发后自动发射 8 个 40kHz 超声波脉冲
//   3. 超声波遇到障碍物(水面/容器底部)反射回来
//   4. HC-SR04 在 ECHO_PIN 输出一个高电平，持续时间 = 声波往返时间
//   5. 用 pulseIn() 测量高电平持续时间(微秒)
//   6. 根据声速计算距离: distance = time × 0.0343cm/us ÷ 2
//
// 【声速说明】
//   常温(20°C)空气中声速约 343 m/s = 0.0343 cm/us
//   实际声速随温度变化: v = 331.3 + 0.606×T(°C) m/s
//   本系统未做温度补偿，室温环境下误差可忽略
//
// 返回值:
//   成功: 距离值(cm)，范围 2.0~400.0
//   失败: -1 (超时无回波 或 距离超出量程范围)
float singleMeasure() {
  // ---- 发送触发脉冲序列 ----
  // digitalWrite(pin, LOW/HIGH) 用于控制数字引脚输出低电平或高电平。
  // 对 HC-SR04 来说，TRIG 引脚必须收到一个短暂的高电平脉冲，才会开始测距。
  digitalWrite(TRIG_PIN, LOW);    // LOW=输出低电平；先拉低5us，把TRIG稳定在低电平，避免上一轮残留高电平影响本次触发
  delayMicroseconds(5);           // delayMicroseconds 是“微秒级延时”；这里等待5us让低电平稳定
  digitalWrite(TRIG_PIN, HIGH);   // 拉高触发脉冲
  delayMicroseconds(10);          // 保持高电平10us；10us=0.01ms，是HC-SR04要求的触发脉冲宽度
  digitalWrite(TRIG_PIN, LOW);    // 再次LOW=结束高电平触发脉冲，形成完整的 LOW→HIGH→LOW 触发信号

  // ---- 测量回波持续时间 ----
  // pulseIn(pin, HIGH, timeout): 等待引脚变为HIGH，然后测量HIGH持续的微秒数
  // 超时设为50000us(50ms)，对应最大距离约 50000×0.0343/2 ≈ 857cm，远超量程
  long dur = pulseIn(ECHO_PIN, HIGH, 50000);

  // 超时或无回波: 传感器前方无障碍物，或距离超出最大量程
  if (dur <= 0) return -1;

  // ---- 距离计算 ----
  // 声波走了一个来回，所以实际距离 = 单程距离 = 总距离 / 2
  // distance = 时间(us) × 声速(0.0343 cm/us) ÷ 2
  float d = dur * 0.0343 / 2.0;

  // ---- 有效范围检验 ----
  // HC-SR04 标称量程: 2cm ~ 400cm
  // 距离 < 2cm: 超声波未充分分离，回波与发射波混叠，读数不可靠
  // 距离 > 400cm: 超出传感器最大探测能力
  return (d >= 2.0 && d <= 400.0) ? d : -1;
}

// ==================== measureDistance() 中值滤波测距 ====================
// 连续执行7次 singleMeasure()，对有效结果排序后取中间值。
//
// 【为什么用中值滤波而不是均值滤波?】
//   中值滤波对离群值(outlier)有天然的免疫力:
//   - 例如7次测量结果: [15.2, 15.3, 15.1, 98.7, 15.4, 15.2, 15.3]
//   - 排序后: [15.1, 15.2, 15.2, 15.3, 15.3, 15.4, 98.7]
//   - 中值 = 15.3 (正确!) ← 异常值98.7完全不影响结果
//   - 均值 = 27.2 (严重偏移!) ← 一个异常值就拉偏了平均
//
// 【采样次数为什么是7次?】
//   奇数次确保中值唯一确定；7次在精度和耗时间取得平衡:
//   单次测距约30ms间隔，7次约 7×30ms = 210ms，不会阻塞主循环太久
//
// 返回值:
//   有有效测量值时: 返回中值距离(cm)
//   全部无效时: 返回上一次的 smoothDistance (保持稳定，避免突变)
float measureDistance() {
  float readings[7];  // 存储有效测量结果
  int count = 0;      // 有效结果计数
  for (int i = 0; i < 7; i++) {
    float d = singleMeasure();         // 执行一次超声波测距
    if (d > 0) { readings[count++] = d; }  // 仅保留有效值(>0)，丢弃-1
    delay(30);  // 每次测量间隔30ms，让超声波余振充分衰减，避免相邻测量互相干扰
  }
  // 如果所有7次测量都失败(极端情况)，返回上一次的平滑值，保持数据连续性
  if (count == 0) return smoothDistance;
  // 对有效值升序排序，然后取中间位置的值作为结果
  sortArray(readings, count);
  return readings[count / 2];
}

// ==================== sortArray() 冒泡排序 ====================
// 对浮点数组进行升序排列，服务于中值滤波的排序需求。
// 使用简单的冒泡排序算法 —— 数据量极小(最多10个元素)，无需更复杂的排序算法。
//
// 参数:
//   arr[] - 待排序的浮点数组
//   n     - 数组中有效元素的个数
//
// 时间复杂度: O(n²)，但 n ≤ 10，实际执行时间可忽略
void sortArray(float arr[], int n) {
  // 外层循环控制排序轮数。n 个元素最多需要 n-1 轮即可完全有序。
  for (int i = 0; i < n - 1; i++)
    // 内层循环比较相邻元素。每完成一轮，当前最大值会被“冒泡”到数组末尾。
    // n - 1 - i 表示末尾已有 i 个元素排好序，不需要重复比较。
    for (int j = 0; j < n - 1 - i; j++)
      // 如果前一个数大于后一个数，就交换它们的位置，实现升序排列。
      if (arr[j] > arr[j + 1]) {
        float t = arr[j];              // 临时变量 t 先保存 arr[j]，避免交换时数据被覆盖
        arr[j] = arr[j + 1];           // 把较小的 arr[j+1] 移到前面
        arr[j + 1] = t;                // 把原来的 arr[j] 放到后面，完成相邻元素交换
      }
}

// ==================== connectWiFi() WiFi连接函数 ====================
// 尝试连接配置的WiFi热点，最多等待15秒(30次×500ms)。
//
// 【重连策略】
//   - 连接失败不会阻塞系统: loop() 继续运行，数据照常采集和屏幕显示
//   - 下次 loop() 检测到 WiFi.status() != WL_CONNECTED 时会再次调用本函数
//   - WiFi断开期间: 数据采集/显示/本地报警正常，仅上传失败
//   - WiFi恢复后: 自动重连，数据继续上传，后端会检测到设备"上线恢复"
void connectWiFi() {
  // 串口输出目标 WiFi 名称，便于调试时确认当前连接的是哪个热点。
  Serial.printf("正在连接WiFi: %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);  // 发起WiFi连接请求；ESP32会在后台尝试认证和获取IP
  int att = 0;                           // att=attempt，表示已经等待/检查连接状态的次数
  // 轮询等待连接结果，每500ms检查一次WiFi状态
  while (WiFi.status() != WL_CONNECTED && att < 30) { delay(500); Serial.print("."); att++; } // 最多等待30次×500ms=15秒
  if (WiFi.status() == WL_CONNECTED)
    // 连接成功后打印 ESP32 从路由器获取到的局域网 IP，后续排查网络时很重要。
    Serial.printf("\nWiFi已连接! IP地址: %s\n", WiFi.localIP().toString().c_str());
  else
    // 连接失败不让程序卡死，下一轮 loop() 检测到未连接时会继续重试。
    Serial.println("\nWiFi连接失败! 将在下次循环中重试");
}

// ==================== uploadData() 数据上传函数 ====================
// 将当前水位数据通过 HTTP POST 发送到后端服务器。
//
// 【上传数据字段说明】
//   {
//     "deviceCode": "WL-004",      ← 设备编号，后端据此识别设备 (DeviceService.getByCode)
//     "waterLevel": 12.5,          ← 当前水位值(cm)，经过滤波和平滑处理后的最终值
//     "rawValue": 185,             ← 传感器原始值(平滑距离×10)，用于数据分析和调试
//     "warningLevel": 15.0,        ← 当前预警阈值(cm)，校准时计算 = 容器高度×60%
//     "dangerLevel": 20.0          ← 当前危险阈值(cm)，校准时计算 = 容器高度×80%
//   }
//
// 【阈值同步机制】
//   上传数据中包含 warningLevel 和 dangerLevel，后端 WaterLevelService.upload() 会:
//   1. 将上报的阈值与数据库中设备的阈值进行比对
//   2. 如果不同(如设备重新校准后容器高度变化)，则自动更新数据库
//   3. 这样前端Web界面始终显示与硬件一致的阈值
//
// 参数:
//   rawValue - 传感器原始值(int)
//   levelCm  - 当前水位(cm, float)
//
// 返回值:
//   true  - HTTP 200响应，上传成功
//   false - WiFi未连接 或 HTTP请求失败 或 非200响应
bool uploadData(int rawValue, float levelCm) {
  // 上传前先检查WiFi状态，避免在未联网时创建HTTP连接造成额外等待。
  // 返回false后，调用方会记录失败次数并在屏幕上显示“失败”。
  if (WiFi.status() != WL_CONNECTED) return false;  // WiFi未连接时跳过上传

  HTTPClient http;
  http.begin(SERVER_URL);                          // 设置目标URL
  http.addHeader("Content-Type", "application/json"); // 设置请求头为JSON格式

  // 构造JSON请求体
  // StaticJsonDocument 是 ArduinoJson 的固定容量 JSON 容器，适合 ESP32，避免频繁动态分配内存。
  // <256> 表示给这个 JSON 文档预留约256字节空间；本项目字段较少，256字节足够。
  StaticJsonDocument<256> doc;  // 在栈上分配256字节的JSON文档缓冲区
  doc["deviceCode"] = DEVICE_CODE;     // 设备编号
  doc["waterLevel"] = levelCm;         // 当前水位(cm)
  doc["rawValue"]   = rawValue;        // 传感器原始值
  doc["warningLevel"] = warnLevel;     // 预警阈值(cm) - 用于阈值同步
  doc["dangerLevel"]  = alarmLevel;    // 危险阈值(cm) - 用于阈值同步

  // 序列化JSON并发送HTTP POST请求
  // payload 表示 HTTP 请求体，也就是最终发给后端的 JSON 字符串。
  String payload;
  serializeJson(doc, payload);         // 将JSON对象序列化为字符串，例如 {"deviceCode":"WL-004","waterLevel":21.5}
  // 这里使用同步POST请求。由于上传周期为5秒，且请求体很小，同步方式足够满足毕业设计演示需求。
  // 如果后续用于高频采集或弱网环境，可以考虑增加超时设置、失败重试或本地缓存补传机制。
  int code = http.POST(payload);       // 把 payload 作为 POST 请求体发送给后端，返回HTTP状态码
  http.end();                          // 释放HTTP连接资源
  return code == 200;                  // HTTP 200 = 服务器成功处理
}

// ==================== checkAlarm() 本地蜂鸣器报警检查 ====================
// 根据当前水位与阈值的关系，驱动蜂鸣器发出不同级别的报警音。
//
// 【报警分级规则】
//   ┌─────────────────────────────────────────────┐
//   │ 水位 ≥ alarmLevel(80%)  → 危险: 急促连响5次 │  buzzerBeep(5, 80, 80)
//   │ 水位 ≥ warnLevel(60%)   → 预警: 短响1次     │  buzzerBeep(1, 150, 0)
//   │ 水位 < warnLevel(60%)   → 正常: 不发声      │
//   └─────────────────────────────────────────────┘
//
// 【与后端报警的区别】
//   - 本地报警(蜂鸣器): 实时声音提醒现场人员，无需网络
//   - 后端报警(AlarmService): 写入数据库，前端Web页面可查看和处理报警记录
//   - 两套机制独立运行，互不影响
//
// 参数:
//   levelCm - 当前水位值(cm)
void checkAlarm(float levelCm) {
  if (levelCm >= alarmLevel) buzzerBeep(5, 80, 80);       // 危险: 80ms响/80ms停 × 5次 = 急促报警
  else if (levelCm >= warnLevel) buzzerBeep(1, 150, 0);   // 预警: 150ms单次短响 = 提醒注意
  // 水位正常时不执行任何操作(静音)
}

// ==================== formatUptime() 运行时长格式化 ====================
// 将系统开机至今的总秒数格式化为 "HH:MM:SS" 字符串。
//
// 参数:
//   buf - 输出缓冲区，至少需要9个字符空间("HH:MM:SS\0")
//
// 计算方式:
//   总秒数 = (当前时间 - 开机时间) / 1000
//   小时 = 总秒数 / 3600
//   分钟 = (总秒数 % 3600) / 60
//   秒   = 总秒数 % 60
void formatUptime(char* buf) {
  unsigned long sec = (millis() - bootTime) / 1000;  // 计算开机至今的总秒数
  int h = sec / 3600;          // 提取小时数
  int m = (sec % 3600) / 60;   // 提取分钟数(去掉整小时部分)
  int s = sec % 60;            // 提取秒数(去掉整分钟部分)
  sprintf(buf, "%02d:%02d:%02d", h, m, s);  // 格式化为 "00:00:00" 形式，不足2位补零
}

// ==================================================================================
//                          TFT 屏幕绘制函数
// ==================================================================================
//
// 【屏幕规格】
//   分辨率: 240 × 240 像素 (正方形)
//   驱动芯片: ST7789
//   接口: SPI
//   颜色深度: 16位 RGB565 (65536色)
//
// 【屏幕布局示意图】(240×240像素)
//   ┌──────────────────────────────────────────────┐ y=0
//   │  WL-004                              (●)WiFi │ 标题栏 (y:0~25, 深色背景)
//   ├──────────────────────────────────────────────┤ y=26 分隔线
//   │  水位                                        │ y=30 标签
//   │                                     ┌──────┐ │
//   │  12.5  cm           45%             │      │ │ 水位大数字 (y:48~95)
//   │                                     │ 垂直 │ │
//   │  [████████████░░░░░░░░░░░]          │ 水位 │ │ 水平进度条 (y:100~112)
//   ├────────────────────────────          │ 条   │─┤ y=120 分隔线
//   │  距离    15.3 cm                    │      │ │ y:126 距离值
//   │  状态    正常                        │      │ │ y:148 状态(正常/预警/报警)
//   ├──────────────────────────────────────┴──────┤ y=170 分隔线
//   │  网络  已连 192.168.0.100                    │ y:175 网络状态
//   │  上传  成功(123)               01:23:45      │ y:197 上传状态 + 运行时长
//   ├──────────────────────────────────────────────┤ y=218
//   │  容器 25.0cm                    W:15 A:20    │ 底部信息栏 (容器高度+阈值)
//   └──────────────────────────────────────────────┘ y=240
//   x=0                            x=195  x=232 x=240
//                                  └─垂直水位条─┘
//
// 【绘制策略】
//   - drawUI(): 绘制静态不变的部分(标题栏、标签文字、边框、分隔线) → 只在启动时调用一次
//   - updateDisplay(): 绘制动态变化的部分(数字、进度条填充、状态文字) → 每次水位变化时调用
//   - updateUploadStatus(): 更新上传结果("成功"/"失败") → 每次上传后调用
//   - updateUptime(): 更新运行时长 → 每秒调用一次
//   这样避免了每次都全屏重绘，减少闪烁并提高刷新效率
//
// 坐标说明:
//   TFT屏幕左上角为(0,0)，x向右增加，y向下增加。
//   本文件中的大部分绘制坐标都是根据240×240屏幕手工布局得到的，
//   如果更换屏幕尺寸或旋转方向，需要重新调整这些坐标。

// ---- drawUI() 绘制主界面静态框架 ----
// 绘制所有不随数据变化的UI元素: 标题栏、标签文字、边框线、底部信息栏
// 仅在 setup() 结束时调用一次，之后只需局部更新动态内容
void drawUI() {
  // fillScreen 会清空整块屏幕；drawUI 只在启动后调用一次，所以允许全屏重绘。
  tft.fillScreen(COLOR_BG);  // 全屏清黑

  // ---- 顶部标题栏 (y: 0~25) ----
  // fillRect(x, y, w, h, color) 表示从左上角(x,y)开始画一个宽w、高h的实心矩形。
  tft.fillRect(0, 0, 240, 26, 0x10A2);  // 深蓝灰色矩形背景 (区分于纯黑主背景)
  // setTextColor(前景色, 背景色) 会在绘制文字时用背景色覆盖旧文字，减少残影。
  tft.setTextColor(COLOR_TITLE, 0x10A2); // 文字颜色=青色, 背景色=深蓝灰(覆盖写入)
  // setTextDatum 设置文字锚点；ML_DATUM 表示坐标点位于文字左侧中线。
  tft.setTextDatum(ML_DATUM);            // 文字左对齐 (Middle Left)
  tft.drawString("WL-004", 10, 13, 2);  // 设备编号，字体大小2
  // 右上角WiFi状态指示灯: 绿色圆点=已连接, 红色圆点=断开
  // 根据 WiFi.status() 判断当前联网状态，并选择绿色或红色。
  uint16_t dotColor = (WiFi.status() == WL_CONNECTED) ? COLOR_NORMAL : COLOR_ALARM;
  tft.fillCircle(220, 13, 5, dotColor);  // 填充圆，圆心(220,13)，半径5

  // ---- 标题栏下方分隔线 ----
  tft.drawLine(0, 26, 240, 26, COLOR_DARKGRAY);  // 水平线，深灰色

  // ---- "水位"中文标签 (y: 30) ----
  drawShuiWei(tft, 10, 30, COLOR_CYAN);  // 使用预渲染位图绘制中文"水位"二字
  tft.setTextColor(COLOR_DARKGRAY, COLOR_BG);
  tft.setTextDatum(MR_DATUM);  // 右对齐 (Middle Right)

  // ---- 水位大数字区域 (y: 50~95) ----
  // 此区域的内容由 updateDisplay() 动态填充，这里不绘制

  // ---- 水平百分比进度条外框 (y: 100~112) ----
  // 圆角矩形边框，内部由 updateDisplay() 根据百分比填充颜色
  // drawRoundRect 只画边框不填充，避免遮挡后续动态进度条。
  tft.drawRoundRect(10, 100, 165, 14, 3, COLOR_DARKGRAY);

  // ---- 右侧垂直水位条外框 (x: 195~232, y: 30~168) ----
  // 模拟水箱的柱状图视觉效果: 外框固定，内部蓝/绿/黄/红色填充高度随水位变化
  tft.drawRect(195, 30, 38, 138, COLOR_GRAY);  // 灰色矩形外框
  // 在垂直水位条上绘制预警线和危险线作为视觉参考
  if (containerHeight > 0) {
    // 计算阈值线在垂直条内的Y坐标 (从底部向上计算)
    // 公式: y = 顶部起点(30) + 条高(136) - 阈值占比 × 可用高度(134)
    // 因为屏幕 y 坐标向下增大，所以水位越高，线条的 y 值越小。
    int wY = 30 + 136 - (int)(warnLevel / containerHeight * 134);   // 预警线Y坐标(黄色)
    int aY = 30 + 136 - (int)(alarmLevel / containerHeight * 134);  // 危险线Y坐标(红色)
    tft.drawLine(195, wY, 232, wY, COLOR_WARN);   // 绘制黄色预警水平线
    tft.drawLine(195, aY, 232, aY, COLOR_ALARM);  // 绘制红色危险水平线
  }

  // ---- 数据区分隔线 (y: 120) ----
  tft.drawLine(10, 120, 185, 120, COLOR_DARKGRAY);

  // ---- "距离"中文标签 (y: 126) ----
  drawJuLi(tft, 10, 126, COLOR_GRAY);    // 位图绘制"距离"

  // ---- "状态"中文标签 (y: 148) ----
  drawZhuangTai(tft, 10, 148, COLOR_GRAY); // 位图绘制"状态"

  // ---- 数据区与网络区分隔线 (y: 170) ----
  tft.drawLine(0, 170, 240, 170, COLOR_DARKGRAY);

  // ---- "网络"中文标签及连接状态 (y: 174~190) ----
  drawWangLuo(tft, 10, 175, COLOR_GRAY);  // 位图绘制"网络"
  tft.setTextDatum(ML_DATUM);  // 文字左对齐
  if (WiFi.status() == WL_CONNECTED) {
    // WiFi 已连接时显示绿色“已连”和 ESP32 当前 IP 地址。
    drawYiLian(tft, 48, 175, COLOR_NORMAL);   // 绿色绘制"已连"
    tft.setTextColor(COLOR_NORMAL, COLOR_BG);
    tft.drawString(WiFi.localIP().toString(), 90, 183, 1);  // 显示设备获得的IP地址
  } else {
    // WiFi 未连接时显示红色“断开”，但本地测量和蜂鸣器仍继续工作。
    drawDuanKai(tft, 48, 175, COLOR_ALARM);   // 红色绘制"断开"
  }

  // ---- "上传"中文标签 (y: 196) ----
  drawShangChuan(tft, 10, 197, COLOR_GRAY);  // 位图绘制"上传"

  // ---- 底部信息栏 (y: 218~238) ----
  // 显示校准数据和阈值信息，帮助现场人员了解当前配置
  tft.fillRect(0, 218, 240, 22, 0x10A2);  // 深色背景(与标题栏风格一致)
  tft.setTextColor(COLOR_DARKGRAY, 0x10A2);
  tft.setTextDatum(ML_DATUM);
  // 左侧: "容器" + 校准高度值
  drawRongQi(tft, 5, 221, COLOR_DARKGRAY);  // 位图绘制"容器"
  char hBuf[16];
  sprintf(hBuf, "%.1fcm", containerHeight);
  tft.drawString(hBuf, 42, 229, 1);  // 字体1(最小)，显示如 "25.0cm"

  // 右侧: 阈值速览 "W:预警值 A:危险值"
  char thBuf[32];
  sprintf(thBuf, "W:%.0f A:%.0f", warnLevel, alarmLevel);  // 如 "W:15 A:20"
  tft.setTextDatum(MR_DATUM);  // 右对齐
  tft.drawString(thBuf, 235, 229, 1);
}

// ---- updateDisplay() 更新屏幕动态内容 ----
// 刷新所有随水位数据变化的UI元素: 水位数字、百分比、进度条、距离值、状态文字、垂直水位条
// 采用"先清除(黑色覆盖)再重绘"的局部刷新策略，避免全屏重绘导致的闪烁
//
// 参数:
//   levelCm - 当前水位值(cm)
//   dist    - 传感器到水面的距离(cm)，即 smoothDistance
//   percent - 水位百分比(0~100%)
void updateDisplay(float levelCm, float dist, float percent) {
  // ---- 清除动态区域 (用黑色矩形覆盖旧内容) ----
  // 这里不调用 fillScreen 全屏清除，因为全屏重绘会造成明显闪烁。
  // 只清除会变化的局部区域，然后重新绘制新内容。
  tft.fillRect(10, 48, 180, 50, COLOR_BG);    // 清除: 水位大数字区
  tft.fillRect(11, 101, 163, 12, COLOR_BG);   // 清除: 水平进度条内部填充
  tft.fillRect(48, 123, 140, 20, COLOR_BG);   // 清除: 距离数值区
  tft.fillRect(48, 145, 140, 20, COLOR_BG);   // 清除: 状态文字区

  // ---- 根据水位级别确定显示颜色 ----
  // 颜色随状态变化: 正常=绿色, 预警=黄色, 危险=红色
  uint16_t color;
  // 先判断危险阈值，再判断预警阈值，因为危险级别优先级更高。
  if (levelCm >= alarmLevel)     { color = COLOR_ALARM; }  // 红色: 水位 ≥ 危险阈值
  else if (levelCm >= warnLevel) { color = COLOR_WARN; }   // 黄色: 水位 ≥ 预警阈值
  else                           { color = COLOR_NORMAL; }  // 绿色: 水位正常

  // ---- 水位大数字显示 (y: 48~95) ----
  tft.setTextColor(color, COLOR_BG);  // 数字颜色跟随状态
  tft.setTextDatum(ML_DATUM);         // 左对齐
  char numBuf[12];
  const char* unit;
  // 自适应单位显示:
  //   水位 < 1cm (噪声阈值以下)  → 显示 "0.0 cm"
  //   水位 ≥ 100cm              → 切换为米(m)，保留2位小数 (如 "1.25 m")
  //   其他                       → 显示厘米(cm)，保留1位小数 (如 "12.5 cm")
  if (levelCm < NOISE_THRESHOLD) {
    // 小于噪声阈值时显示 0.0cm，避免把假水位显示给用户。
    sprintf(numBuf, "0.0");
    unit = "cm";
  } else if (levelCm >= 100.0) {
    // 超过 100cm 时用 m 显示，避免大数字占用过多屏幕宽度。
    sprintf(numBuf, "%.2f", levelCm / 100.0);  // cm 转 m
    unit = "m";
  } else {
    // 常规水位使用 cm，保留 1 位小数。
    sprintf(numBuf, "%.1f", levelCm);
    unit = "cm";
  }
  // drawString 返回绘制文字占用的像素宽度，后面用它把单位紧贴数字右侧。
  int numW = tft.drawString(numBuf, 10, 72, 6);  // 字体6(最大号)显示数值，返回文字像素宽度
  tft.drawString(unit, 10 + numW + 4, 84, 4);    // 在数字右侧4px处显示单位，字体4

  // 百分比文字 (数字区右上角，灰色小字)
  tft.setTextColor(COLOR_GRAY, COLOR_BG);
  tft.setTextDatum(MR_DATUM);  // 右对齐
  char pctBuf[8];
  sprintf(pctBuf, "%d%%", (int)percent);
  tft.drawString(pctBuf, 185, 54, 2);  // 如 "45%"

  // ---- 水平百分比进度条 (y: 100~112) ----
  // 进度条总宽161px，根据百分比计算填充宽度
  // percent=0 时 barW=0，不绘制填充；percent=100 时填满 161px。
  int barW = (int)(percent / 100.0 * 161);
  if (barW > 161) barW = 161;  // 防溢出
  if (barW > 0) {
    // 逐像素列绘制渐变色进度条，直观反映水位所处区间:
    //   0%~50%  → 绿色 (安全区)
    //   50%~75% → 黄色 (接近预警)
    //   75%~100%→ 红色 (接近/超过危险)
    for (int x = 0; x < barW; x++) {
      // ratio 表示当前绘制列处在进度条的哪个百分比位置。
      float ratio = (float)x / 161.0;  // 当前像素在进度条中的位置比例
      uint16_t barColor;
      if (ratio < 0.5)       { barColor = COLOR_NORMAL; }  // 前半段: 绿色
      else if (ratio < 0.75) { barColor = COLOR_WARN; }    // 中间段: 黄色
      else                   { barColor = COLOR_ALARM; }   // 后半段: 红色
      tft.drawLine(12 + x, 102, 12 + x, 112, barColor);   // 画一条垂直线(宽1px)
    }
  }

  // ---- 距离数值显示 (y: 126~140) ----
  tft.setTextColor(COLOR_TEXT, COLOR_BG);  // 白色文字
  tft.setTextDatum(ML_DATUM);              // 左对齐
  char distBuf[20];
  if (dist >= 100.0) {
    sprintf(distBuf, "%.2f m", dist / 100.0);  // ≥100cm 自动转换为米
  } else {
    sprintf(distBuf, "%.1f cm", dist);          // 正常显示厘米
  }
  tft.drawString(distBuf, 48, 133, 2);  // 显示在"距离"标签右侧

  // ---- 状态中文显示 (y: 148~165) ----
  // 使用位图函数绘制对应的中文状态文字，颜色跟随状态级别
  if (levelCm >= alarmLevel) {
    drawBaoJing(tft, 48, 148, COLOR_ALARM);   // 红色绘制"报警"
    tft.setTextColor(COLOR_ALARM, COLOR_BG);
    tft.drawString("!", 88, 156, 2);          // 附加红色感叹号，增强视觉警示
  } else if (levelCm >= warnLevel) {
    drawYuJing(tft, 48, 148, COLOR_WARN);     // 黄色绘制"预警"
  } else {
    drawZhengChang(tft, 48, 148, COLOR_NORMAL); // 绿色绘制"正常"
  }

  // ---- 右侧垂直水位条更新 (x: 195~232, y: 30~168) ----
  // 垂直水位条相当于一个小型“水箱示意图”，用于让现场人员快速判断水位占容器高度的比例。
  // 它和水平进度条显示同一个 percent，只是呈现方向不同。
  // 先清空内部，再画阈值线和水位填充，避免旧水位残留。
  tft.fillRect(196, 31, 36, 136, COLOR_BG);  // 先清除垂直条内部的旧填充

  // 重绘阈值参考线 (被清除操作覆盖了，需要重画)
  if (containerHeight > 0) {
    // 阈值线位置同 drawUI() 中的计算方式保持一致。
    int wY = 30 + 136 - (int)(warnLevel / containerHeight * 134);
    int aY = 30 + 136 - (int)(alarmLevel / containerHeight * 134);
    tft.drawLine(196, wY, 231, wY, COLOR_WARN);   // 黄色预警线
    tft.drawLine(196, aY, 231, aY, COLOR_ALARM);  // 红色危险线
  }

  // 从底部向上填充水位条: 高度与百分比成正比，颜色跟随当前状态
  // barH 是水位条填充高度，percent 越大，填充高度越高。
  int barH = (int)(percent / 100.0 * 134);  // 可用填充高度最大134px
  if (barH > 134) barH = 134;
  if (barH > 0) {
    // fillRect 从左上角开始画: x=196, y=从顶部偏移(未填充部分)开始, 宽36, 高barH
    // y=31+(136-barH) 表示从底部向上填充，而不是从顶部向下填充。
    tft.fillRect(196, 31 + (136 - barH), 36, barH, color);
  }
}

// ---- updateUploadStatus() 更新上传状态显示 ----
// 在屏幕"上传"标签右侧显示最近一次上传的结果
//
// 参数:
//   ok - true=本次上传成功(显示绿色"成功"), false=上传失败(显示红色"失败")
void updateUploadStatus(bool ok) {
  // 上传状态区域只显示最近一次结果，因此每次先清除旧文字。
  tft.fillRect(48, 194, 100, 20, COLOR_BG);  // 清除旧的上传状态文字区域

  if (ok) {
    // ok=true 表示 HTTP 200，后端成功接收并处理数据。
    drawChengGong(tft, 48, 197, COLOR_NORMAL);   // 绿色位图绘制"成功"
  } else {
    // ok=false 可能是 WiFi 未连接、HTTP 请求失败或后端返回非 200。
    drawShiBai(tft, 48, 197, COLOR_ALARM);        // 红色位图绘制"失败"
  }

  // 在状态文字右侧显示累计上传次数，如 "(123)"
  // 这里显示的是上传尝试次数，不是成功次数；失败次数保存在 uploadFailCount 中。
  // 如果需要计算成功率，可以用 (uploadCount - uploadFailCount) / uploadCount。
  tft.setTextDatum(ML_DATUM);
  tft.setTextColor(COLOR_DARKGRAY, COLOR_BG);
  char cntBuf[20];
  sprintf(cntBuf, "(%d)", uploadCount);
  tft.drawString(cntBuf, 88, 205, 1);  // 字体1(最小)，深灰色
}

// ---- updateUptime() 每秒刷新运行时长显示 ----
// 在屏幕右下方显示系统运行时长，格式为 HH:MM:SS
// 运行时长用于判断设备是否发生过重启：
//   如果运行时长突然从很大变回 00:00:xx，说明设备可能断电、复位或程序异常重启。
void updateUptime() {
  // 运行时长每秒更新，采用局部清除，避免影响水位显示区域。
  tft.fillRect(150, 197, 45, 16, COLOR_BG);  // 清除旧的时间文字(45×16px区域)
  char uptBuf[12];
  formatUptime(uptBuf);  // 将累计秒数格式化为 "HH:MM:SS" 字符串
  tft.setTextColor(COLOR_DARKGRAY, COLOR_BG);  // 深灰色，不抢视觉焦点
  tft.setTextDatum(MR_DATUM);  // 右对齐
  tft.drawString(uptBuf, 185, 205, 1);  // 在x=185处右对齐显示
}
