#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <task.h>
#include <queue.h>
#include "hw_camera.h"
#include <drowsiness_inferencing.h>
#include "edge-impulse-sdk/dsp/image/image.hpp"
#include <ArduinoJson.h>
#include <time.h>

// Constants
const char *ssid = "-"; // Enter your Wi-Fi name
const char *password = "-";  // Enter Wi-Fi password

#define TAG     "main"

// MQTT Broker
const char *mqtt_broker = "broker.hivemq.com";
const char *topic = "----------";
const char *mqtt_username = "----------";
const char *topicHB = "------/heartbeat/dev_01";
const char *topicState = "-------/status/dev_01";
const char *topicCommand = "-------/command/dev_01";
const int mqtt_port = 1883;

WiFiClient espClient;
PubSubClient client(espClient);
StaticJsonDocument<200> json_doc;
StaticJsonDocument<200> state_doc;

#define EI_CAMERA_RAW_FRAME_BUFFER_COLS           240
#define EI_CAMERA_RAW_FRAME_BUFFER_ROWS           240
#define EI_CAMERA_FRAME_BYTE_SIZE                 3
#define BMP_BUF_SIZE                             (EI_CAMERA_RAW_FRAME_BUFFER_COLS * EI_CAMERA_RAW_FRAME_BUFFER_ROWS * EI_CAMERA_FRAME_BYTE_SIZE)

// Static variables
static uint8_t *bmp_buf;

xTaskHandle captureTaskHandle = NULL;
bool CMD = false;

// Function prototypes
void callback(char *topic, byte *payload, unsigned int length);
void publishMessage(const char *msg);
void pubHBMessage(const char *msg);
void publishHeartbeat();
void pubState(const char *msg);
void SubCMD();
void ei_prepare_feature(uint8_t *img_buf, signal_t *signal);
int ei_get_feature_callback(size_t offset, size_t length, float *out_ptr);
void ei_use_result(ei_impulse_result_t result);
void captureAndProcessImage(void *parameter);

void setup() {
    Serial.begin(115200);

    // Connect to Wi-Fi
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.println("Connecting to WiFi..");
    }
    Serial.println("Connected to the Wi-Fi network");

    // Initialize camera
    hw_camera_init();

    // Allocate memory for the camera snapshot buffer
    bmp_buf = (uint8_t *)malloc(BMP_BUF_SIZE);
    if (!bmp_buf) {
        Serial.println("Failed to allocate memory for bmp_buf");
        while (1)
            ; // Loop indefinitely if memory allocation fails
    }

    // Connect to MQTT broker
    client.setServer(mqtt_broker, mqtt_port);
    client.setCallback(callback);

    while (!client.connected()) {
        String client_id = "esp32-client-";
        client_id += String(WiFi.macAddress());
        Serial.printf("The client %s connects to the public MQTT broker\n", client_id.c_str());
        if (client.connect(mqtt_username)) {
            Serial.println("Public MQTT broker connected");
        } else {
            Serial.print("failed with state ");
            Serial.print(client.state());
            delay(2000);
        }
    }
    // Initialize time
    configTime(0, 0, "pool.ntp.org"); // Set time via NTP
    Serial.println("Waiting for time sync...");
    while (!time(nullptr)) {
        delay(1000);
        Serial.println("Waiting for time sync...");
    }
    Serial.println("Time synchronized.");

    SubCMD();

    // Start a timer to capture and process image every 1 second
    xTaskCreatePinnedToCore(
        captureAndProcessImage,   /* Function to implement the task */
        "ImageCaptureTask",       /* Name of the task */
        10000,                    /* Stack size in words */
        NULL,                     /* Task input parameter (cast to void*) */
        1,                        /* Priority of the task */
        NULL,                     /* Task handle */
        0                         /* Core where the task should run */
    );


}

void loop() {
    publishHeartbeat();
    delay(1000);

    if (!client.connected()) {
        // Reconnect to MQTT broker if connection is lost
        while (!client.connected()) {
            if (client.connect(mqtt_username)) {
                Serial.println("Reconnected to MQTT broker");
                client.setCallback(callback);
                SubCMD(); // Resubscribe to command topic after reconnecting
            } else {
                Serial.print("Failed to reconnect to MQTT broker, rc=");
                Serial.print(client.state());
                Serial.println(" Retrying in 5 seconds...");
                delay(5000);
            }
        }
    }

    client.loop();
}

void SubCMD() {
    client.subscribe(topicCommand);
}

void callback(char* topic, byte* payload, unsigned int length) {
    Serial.print("Message arrived in topic: ");
    Serial.println(topic);

    Serial.print("Payload: ");
    // Convert payload to a string
    String message;
    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }

    // Parse JSON
    DynamicJsonDocument doc(256); // Adjust the size as needed
    DeserializationError error = deserializeJson(doc, message);
    if (error) {
        Serial.print("deserializeJson() failed: ");
        Serial.println(error.c_str());
        return;
    }

    // Check if "CMD" exists in the JSON message and its value is true
    if (doc.containsKey("CMD")) {
        CMD = doc["CMD"].as<bool>();
        Serial.print("CMD set to: ");
        Serial.println(CMD ? "true" : "false");
    }
}


void captureAndProcessImage(void *parameter) {
    while (true) {
        uint32_t Tstart, elapsed_time;
        uint32_t width, height;
        
        Tstart = millis();
        // get raw data
        //Serial.println(CMD);
        if (CMD == true){
            state_doc["status"] = "activated";
            pubState(state_doc.as<String>().c_str());
            Serial.println("Taking snapshot...");
            hw_camera_raw_snapshot(bmp_buf, &width, &height);
            elapsed_time = millis() - Tstart;
            Serial.printf("Snapshot taken (%d) width: %d, height: %d\n", elapsed_time, width, height);
            // prepare feature
            Tstart = millis();
            ei::signal_t signal;
            ei_prepare_feature(bmp_buf, &signal);
            elapsed_time = millis() - Tstart;
            Serial.printf("Feature taken (%d)\n", elapsed_time);
            // run classifier
            Tstart = millis();
            ei_impulse_result_t result = {0};
            bool debug_nn = false;
            run_classifier(&signal, &result, debug_nn);
            elapsed_time = millis() - Tstart;
            Serial.printf("Classification done (%d)\n", elapsed_time);
            // use result
            ei_use_result(result);
            Serial.println("-----------------------");
            
        }
        else{
            Serial.println("Waiting for CMD ...");
            state_doc["status"] = "online";
            pubState(state_doc.as<String>().c_str());
        }
        // Wait for 1 second before capturing the next image
        delay(1000);
    }
}

void ei_prepare_feature(uint8_t *img_buf, signal_t *signal) {
    signal->total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
    signal->get_data = &ei_get_feature_callback;
    if ((EI_CAMERA_RAW_FRAME_BUFFER_ROWS != EI_CLASSIFIER_INPUT_WIDTH) || (EI_CAMERA_RAW_FRAME_BUFFER_COLS != EI_CLASSIFIER_INPUT_HEIGHT)) {
        ei::image::processing::crop_and_interpolate_rgb888(
            img_buf,
            EI_CAMERA_RAW_FRAME_BUFFER_COLS,
            EI_CAMERA_RAW_FRAME_BUFFER_ROWS,
            img_buf,
            EI_CLASSIFIER_INPUT_WIDTH,
            EI_CLASSIFIER_INPUT_HEIGHT
        );
    }
}

int ei_get_feature_callback(size_t offset, size_t length, float *out_ptr) {
    size_t pixel_ix = offset * 3;
    size_t pixels_left = length;
    size_t out_ptr_ix = 0;

    while (pixels_left != 0) {
        out_ptr[out_ptr_ix] = (bmp_buf[pixel_ix] << 16) + (bmp_buf[pixel_ix + 1] << 8) + bmp_buf[pixel_ix + 2];

        out_ptr_ix++;
        pixel_ix += 3;
        pixels_left--;
    }
    return 0;
}

void ei_use_result(ei_impulse_result_t result) {
    bool bb_found = result.bounding_boxes[0].value > 0;
    int close_count = 0; // Counter for "Close" labels
    for (size_t ix = 0; ix < result.bounding_boxes_count; ix++) {
        auto bb = result.bounding_boxes[ix];
        if (bb.value == 0) {
            continue;
        }
        Serial.printf("%s (%f) ", bb.label, bb.value);
        if (bb.label == "Open") {
            json_doc.clear();
            json_doc["eye_status"] = "0";
            json_doc["alarm_status"] = "0";
            json_doc["timestamp"] = time(nullptr);
            // Publish the bounding box label
            publishMessage(json_doc.as<String>().c_str());
            close_count = 0; // Reset close count if Open label detected
        }
        else if (bb.label == "Close") {
            close_count++; // Increment close count for "Close" labels
            if (close_count >= 3) {
                Serial.println("Alarm on");
                json_doc.clear();
                json_doc["eye_status"] = "1";
                json_doc["alarm_status"] = "0"; // Set alarm status to "1"
                json_doc["timestamp"] = time(nullptr);
                // Publish the alarm status
                publishMessage(json_doc.as<String>().c_str());
            } else {
                json_doc.clear();
                json_doc["eye_status"] = "1";
                json_doc["alarm_status"] = "0";
                json_doc["timestamp"] = time(nullptr);
                // Publish the bounding box label
                publishMessage(json_doc.as<String>().c_str());
            }
        }
    }
    if (!bb_found) {
        Serial.println("No objects found");
    }
}

void publishMessage(const char *msg) {
    client.publish(topic, msg);
}

void pubHBMessage(const char *msg) {
    client.publish(topicHB, msg);
}

void publishHeartbeat() {
    StaticJsonDocument<200> heartbeat_doc;
    heartbeat_doc["heartbeat"] = "heartbeat";
    heartbeat_doc["timestamp"] = time(nullptr);
    pubHBMessage(heartbeat_doc.as<String>().c_str());
}

void pubState(const char *msg) {
    client.publish(topicState, msg);
}
