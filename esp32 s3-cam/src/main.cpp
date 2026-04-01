#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"

// ==========================================
// 1. 配置你的 WiFi 网络
// ==========================================
const char* ssid = "20050801";         // 替换为你的WiFi名称
const char* password = "20050801"; // 替换为你的WiFi密码

// ==========================================
// 2. 填入你之前验证成功的摄像头引脚
// ==========================================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM     4
#define SIOC_GPIO_NUM     5
#define Y9_GPIO_NUM       16
#define Y8_GPIO_NUM       17
#define Y7_GPIO_NUM       18
#define Y6_GPIO_NUM       12
#define Y5_GPIO_NUM       10
#define Y4_GPIO_NUM       8
#define Y3_GPIO_NUM       9
#define Y2_GPIO_NUM       11
#define VSYNC_GPIO_NUM    6
#define HREF_GPIO_NUM     7
#define PCLK_GPIO_NUM     13

httpd_handle_t stream_httpd = NULL;

// ==========================================
// 视频流处理函数 (加入了软件 JPEG 压缩)
// ==========================================
esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;
    char part_buf[128];
    uint8_t * _jpg_buf = NULL;
    size_t _jpg_buf_len = 0;

    res = httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=123456789000000000000987654321");
    if (res != ESP_OK) return res;

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("获取画面失败");
            res = ESP_FAIL;
            break;
        } 
        
        // 【核心修改】如果摄像头输出的不是 JPEG，就用 S3 芯片软件压缩成 JPEG
        if (fb->format != PIXFORMAT_JPEG) {
            // 参数 80 是 JPEG 压缩质量 (0-100)
            bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
            esp_camera_fb_return(fb);
            fb = NULL;
            if (!jpeg_converted) {
                Serial.println("JPEG软件压缩失败");
                res = ESP_FAIL;
                break;
            }
        } else {
            _jpg_buf = fb->buf;
            _jpg_buf_len = fb->len;
        }

        if (res == ESP_OK) {
            size_t hlen = snprintf((char *)part_buf, 128, "\r\n--123456789000000000000987654321\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", _jpg_buf_len);
            res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, "\r\n", 2);
        }

        // 释放内存
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }
        
        if (res != ESP_OK) break;
    }
    return res;
}

void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 81;

    httpd_uri_t stream_uri = {
        .uri       = "/stream",
        .method    = HTTP_GET,
        .handler   = stream_handler,
        .user_ctx  = NULL
    };

    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
    }
}

void setup() {
    Serial.begin(115200);
    // 加上下面这行，给电脑 3 秒钟的时间来重新识别 USB 串口
    delay(3000); 
    
    Serial.println("\n\n===============================");
    Serial.println("ESP32-S3 代码开始运行！");
    Serial.println("===============================");
    
    // ... 保持后面的摄像头配置代码不变 ...
    Serial.setDebugOutput(false);
    Serial.println();

    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    
    // 【核心修改】将格式改为原始彩色像素 RGB565，避开 GC2145 不支持 JPEG 的问题
    config.pixel_format = PIXFORMAT_RGB565; 
    
    // 由于软件压缩比较吃力，初次测试先使用 QVGA (320x240) 分辨率确保流畅
    config.frame_size = FRAMESIZE_QVGA; 
    config.jpeg_quality = 12; // 此参数在非JPEG模式下会被忽略
    config.fb_count = 1; 

    // 初始化摄像头
    // 初始化摄像头
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        // 如果失败，就一直循环打印错误，直到你看到为止！
        while(true) { 
            Serial.printf("摄像头初始化失败，错误码: 0x%x\n", err);
            delay(2000); 
        }
    }
    Serial.println("摄像头初始化成功！");

    // 连接 WiFi
    WiFi.begin(ssid, password);
    Serial.print("正在连接 WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("");
    Serial.println("WiFi 连接成功！");

    // 启动视频流服务器
    startCameraServer();

    Serial.println("=========================================");
    Serial.print(">>> 视频流地址: http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81/stream <<<");
    Serial.println("=========================================");
}

void loop() {
    delay(10000);
}