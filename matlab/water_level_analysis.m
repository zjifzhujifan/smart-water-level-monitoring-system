%% 水位数据分析脚本
% 功能: 从服务器导出CSV数据，进行统计分析和可视化
% 作者: 毕业设计
% 日期: 2026
%
% 使用说明:
% 1. 优先读取当前目录下的 water_level_data.csv；
% 2. 如果本地文件不存在，则自动登录后端并调用导出接口下载 CSV；
% 3. 生成水位曲线、移动平均、直方图、趋势拟合和报警分布图；
% 4. 将关键统计结果写入 analysis_results.txt，便于论文测试章节引用。

clear; clc; close all;

%% ========== 0. 后端连接配置 ==========
% 出于公开仓库安全考虑，脚本不硬编码账号和密码。
% 可通过环境变量配置:
%   WLM_API_BASE_URL=http://localhost:8080
%   WLM_USERNAME=your_username
%   WLM_PASSWORD=your_password
apiBaseUrl = getenv('WLM_API_BASE_URL');
if strlength(string(apiBaseUrl)) == 0
    apiBaseUrl = 'http://localhost:8080';
end
apiBaseUrl = char(regexprep(string(apiBaseUrl), '/+$', ''));
apiUsername = getenv('WLM_USERNAME');
apiPassword = getenv('WLM_PASSWORD');

%% ========== 1. 数据读取 ==========
fprintf('===== 水位数据分析 =====\n');

% 从CSV文件读取数据（先通过浏览器下载: http://localhost:8080/api/export/csv）
% 或者直接从服务器API读取
try
    % 方式1: 从本地CSV文件读取
    data = readtable('water_level_data.csv');
    fprintf('从CSV文件读取数据: %d 条记录\n', height(data));
catch
    % 方式2: 从服务器API直接读取（需要先登录获取Token）
    fprintf('尝试从服务器读取数据...\n');

    % Step 1: 登录获取 JWT Token
    if strlength(string(apiUsername)) == 0
        apiUsername = input('请输入后端用户名: ', 's');
    end
    if strlength(string(apiPassword)) == 0
        apiPassword = input('请输入后端密码: ', 's');
    end
    loginUrl = [apiBaseUrl '/api/auth/login'];
    loginData = struct('username', char(apiUsername), 'password', char(apiPassword));
    loginOptions = weboptions('MediaType', 'application/json', 'ContentType', 'json');
    response = webwrite(loginUrl, loginData, loginOptions);
    token = response.token;
    fprintf('登录成功，已获取Token\n');

    % Step 2: 携带 Token 请求导出接口
    url = [apiBaseUrl '/api/export/csv'];
    filename = 'water_level_data.csv';
    exportOptions = weboptions('HeaderFields', {'Authorization', ['Bearer ' token]});
    websave(filename, url, exportOptions);
    data = readtable(filename);
    fprintf('从服务器读取数据: %d 条记录\n', height(data));
end

% 解析时间。
% CSV 中 collect_time 是后端格式化后的字符串，这里转换为 datetime 后才能作为横轴绘图。
data.collect_time = datetime(data.collect_time, 'InputFormat', 'yyyy-MM-dd HH:mm:ss');

% 获取水位数据和时间戳，后续所有统计和绘图都围绕这两个序列展开。
waterLevel = data.water_level;
timeStamps = data.collect_time;

%% ========== 2. 基本统计分析 ==========
fprintf('\n--- 基本统计 ---\n');
fprintf('数据总量: %d\n', length(waterLevel));
fprintf('最大水位: %.2f cm\n', max(waterLevel));
fprintf('最小水位: %.2f cm\n', min(waterLevel));
fprintf('平均水位: %.2f cm\n', mean(waterLevel));
fprintf('标准差: %.2f cm\n', std(waterLevel));
fprintf('中位数: %.2f cm\n', median(waterLevel));

%% ========== 3. 水位变化曲线 ==========
figure('Name', '水位变化曲线', 'Position', [100, 100, 1200, 400]);

plot(timeStamps, waterLevel, 'b-', 'LineWidth', 1);
hold on;

% 绘制预警线和危险线。
% 注意: 这里使用固定 80/100 cm 作为离线分析口径；若要完全跟随设备阈值，
% 可以从导出的设备表或后端接口中读取对应设备的 warning_level/danger_level。
warningLevel = 80;  % 预警阈值
dangerLevel  = 100; % 危险阈值

yline(warningLevel, '--', '预警线', 'Color', [0.9 0.6 0], 'LineWidth', 1.5, 'LabelHorizontalAlignment', 'left');
yline(dangerLevel,  '--', '危险线', 'Color', [0.9 0.2 0], 'LineWidth', 1.5, 'LabelHorizontalAlignment', 'left');

xlabel('时间');
ylabel('水位 (cm)');
title('水位变化趋势');
grid on;
legend('实测水位', '预警线', '危险线', 'Location', 'best');
hold off;

%% ========== 4. 移动平均平滑 ==========
figure('Name', '平滑处理', 'Position', [100, 550, 1200, 400]);

% 移动平均窗口。
% 窗口越大曲线越平滑，但短时间突变会被削弱；这里取 5 兼顾平滑和响应。
windowSize = 5;
smoothedLevel = movmean(waterLevel, windowSize);

plot(timeStamps, waterLevel, 'b-', 'LineWidth', 0.5, 'Color', [0.7 0.7 1]);
hold on;
plot(timeStamps, smoothedLevel, 'r-', 'LineWidth', 2);

xlabel('时间');
ylabel('水位 (cm)');
title(sprintf('移动平均平滑 (窗口=%d)', windowSize));
legend('原始数据', '平滑曲线', 'Location', 'best');
grid on;
hold off;

%% ========== 5. 水位分布直方图 ==========
figure('Name', '水位分布', 'Position', [100, 100, 600, 400]);

histogram(waterLevel, 30, 'FaceColor', [0.3 0.6 0.9], 'EdgeColor', 'w');
xlabel('水位 (cm)');
ylabel('频次');
title('水位分布直方图');
grid on;

% 添加均值线
xline(mean(waterLevel), 'r--', sprintf('均值=%.1f', mean(waterLevel)), 'LineWidth', 2);

%% ========== 6. 趋势分析 (线性拟合) ==========
figure('Name', '趋势分析', 'Position', [750, 100, 600, 400]);

% 将时间转为数值（分钟）。
% polyfit 只能处理数值自变量，不能直接对 datetime 做线性拟合。
timeNumeric = minutes(timeStamps - timeStamps(1));

% 线性拟合。
% p(1) 是趋势斜率，单位为 cm/min；p(2) 是截距。
p = polyfit(timeNumeric, waterLevel, 1);
trendLine = polyval(p, timeNumeric);

plot(timeStamps, waterLevel, 'b.', 'MarkerSize', 4);
hold on;
plot(timeStamps, trendLine, 'r-', 'LineWidth', 2);

xlabel('时间');
ylabel('水位 (cm)');
title('水位线性趋势分析');

if p(1) > 0
    trendText = sprintf('上升趋势: +%.4f cm/min', p(1));
else
    trendText = sprintf('下降趋势: %.4f cm/min', p(1));
end
legend('实测数据', trendText, 'Location', 'best');
grid on;
hold off;

%% ========== 7. 报警统计 ==========
% 按固定阈值重新划分状态，用于与论文表格中的正常/预警/危险占比对应。
normalCount  = sum(waterLevel < warningLevel);
warningCount = sum(waterLevel >= warningLevel & waterLevel < dangerLevel);
dangerCount  = sum(waterLevel >= dangerLevel);

fprintf('\n--- 报警统计 ---\n');
fprintf('正常: %d 次 (%.1f%%)\n', normalCount, normalCount/length(waterLevel)*100);
fprintf('预警: %d 次 (%.1f%%)\n', warningCount, warningCount/length(waterLevel)*100);
fprintf('危险: %d 次 (%.1f%%)\n', dangerCount, dangerCount/length(waterLevel)*100);

% 饼图
figure('Name', '报警分布', 'Position', [750, 550, 500, 400]);
labels = {'正常', '预警', '危险'};
counts = [normalCount, warningCount, dangerCount];
colors = [0.4 0.8 0.4; 0.9 0.7 0.2; 0.9 0.3 0.3];

% 过滤掉数量为0的类别
validIdx = counts > 0;
pie(counts(validIdx), labels(validIdx));
colororder(colors(validIdx, :));
title('水位状态分布');

%% ========== 8. 保存分析结果 ==========
fprintf('\n分析完成！图表已生成。\n');

% 保存统计结果到文件。
% 文件内容为纯文本，适合直接复制到论文测试结果分析或作为运行证据归档。
resultsFile = 'analysis_results.txt';
fid = fopen(resultsFile, 'w');
fprintf(fid, '水位数据分析报告\n');
fprintf(fid, '================\n');
fprintf(fid, '分析时间: %s\n\n', datestr(now));
fprintf(fid, '数据总量: %d\n', length(waterLevel));
fprintf(fid, '最大水位: %.2f cm\n', max(waterLevel));
fprintf(fid, '最小水位: %.2f cm\n', min(waterLevel));
fprintf(fid, '平均水位: %.2f cm\n', mean(waterLevel));
fprintf(fid, '标准差: %.2f cm\n', std(waterLevel));
fprintf(fid, '趋势斜率: %.6f cm/min\n', p(1));
fprintf(fid, '\n报警统计:\n');
fprintf(fid, '正常: %d (%.1f%%)\n', normalCount, normalCount/length(waterLevel)*100);
fprintf(fid, '预警: %d (%.1f%%)\n', warningCount, warningCount/length(waterLevel)*100);
fprintf(fid, '危险: %d (%.1f%%)\n', dangerCount, dangerCount/length(waterLevel)*100);
fclose(fid);
fprintf('分析报告已保存到: %s\n', resultsFile);
