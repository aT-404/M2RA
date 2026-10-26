/*
 * RoboticHand ESP8266 Firmware
 * Project: 5-DOF Anthropomorphic Robotic Prosthetic Hand
 * Developers: Albert Toj Kayyalaparambil, Vivek Viswanath, Ronith Promy, Shifa Mariyam
 * Hardware: ESP8266 NodeMCU, 5x Servos (SG90/MG90S), SH1106 I2C OLED Display
 */

#include <Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <DNSServer.h>
#include <ESP8266WebServer.h>
#include <Adafruit_SH110X.h>
#include <FS.h>
#include <ESP8266mDNS.h>
#include <ArduinoJson.h>
#include <ESP8266WiFiMulti.h>
#include <WiFiUdp.h>

ESP8266WiFiMulti wifiMulti;
JsonDocument Config;
bool debug = true;
bool AP_ON = false;
long displayLockUpTo = 0;

WiFiUDP udpServer;
const int UDP_PORT = 8888;
unsigned long udpCooldownUntil = 0;
const unsigned long UDP_COOLDOWN_MS = 2000;

bool gestureAnimating = false;
unsigned long gestureAnimTimer = 0;
int gestureStep = 0;
const int WAVE_DELAY = 100;

Servo Servo_Thumb;
Servo Servo_Index;
Servo Servo_Middle;
Servo Servo_Ring;
Servo Servo_Pinky;

DNSServer dnsServer;
ESP8266WebServer webServer(80);

String replaceSubstring(String original, String toReplace, String replacement) {
    int pos = original.indexOf(toReplace);
    while (pos != -1) { // Keep replacing until no more occurrences are found
        original = original.substring(0, pos) + replacement + original.substring(pos + toReplace.length());
        pos = original.indexOf(toReplace); // Find the next occurrence
    }
    return original;
}

void saveConfig(){
	File ConfigFile = SPIFFS.open("/config.json", "w");
	serializeJson(Config, ConfigFile);
	ConfigFile.close();
}

void saveLoadDefaultConfig(){
	Serial.println("Saving default configuration");
	deserializeJson(Config, "{\"servo1\": 16,\"servo2\": 0,\"servo3\": 14,\"servo4\": 12,\"servo5\": 13,\"OLED_SDA\": 4,\"OLED_SCL\": 5,\"WifiMulti\": [],\"SelfAP\": {\"ssid\": \"ServoGrip\",\"password\": \"Servo@Grip\"}}");
	Config["OLED_SDA"] = D1;
	Config["OLED_SCL"] = D2;
    saveConfig();
	Serial.println("Loaded default configuration: ");
	if(debug){serializeJsonPretty(Config, Serial);}
}

void getConfig() {
    if (SPIFFS.exists("/config.json")) {
        File ConfigFile = SPIFFS.open("/config.json", "r");
        if (ConfigFile) {
            DeserializationError error = deserializeJson(Config, ConfigFile);
			if (error) {
				Serial.println("Error in deserializing JSON file, Loading Default Config");
				saveLoadDefaultConfig();
			} else {
				Serial.println("Config Loaded successfully");
				if(debug){serializeJsonPretty(Config, Serial);}
			}
        	ConfigFile.close();
        } else {
            Serial.println("Failed to open the config file.");
        }
    }
	else{
        Serial.println("File Config.json not found, Saving and creating default config file");
		saveLoadDefaultConfig();
	}
}

//WiFi Stuff
void addAPtoWiFiMulti(String ssid, String pass=""){
    bool found = false;
    for (int x = 0; x < Config["WifiMulti"].size(); x++) {
        if (Config["WifiMulti"][x][0].as<String>() == ssid) {
            Config["WifiMulti"][x][1] = pass;
            found = true;
            break;
        }
    }
    if (!found) {
        JsonArray newWiFiNetwork = Config["WifiMulti"].createNestedArray();
        newWiFiNetwork.add(ssid);
        newWiFiNetwork.add(pass);
    }
    saveConfig();
}

// Display Stuff
Adafruit_SH1106G display(128, 64, &Wire, -1);

int WiFiMultiConnectingLoading_dots = 0;
void WiFiMultiConnectingLoading(){
    display.clearDisplay();
    display.setCursor(0, 0);
    display.println("Connecting To WiFi");
    if (WiFiMultiConnectingLoading_dots>5) {
        WiFiMultiConnectingLoading_dots = 1;
    }
    for (int x = 1; x<=WiFiMultiConnectingLoading_dots; x++) {
        display.print(".");
    }
    WiFiMultiConnectingLoading_dots++;
    display.display();
}

int changeInterval = 10000;
void UpdateOLED(){
    if (millis()<displayLockUpTo) {
        return;
    }
    display.clearDisplay();
    display.setCursor(0, 0);
    display.setTextSize(1);
    if((millis()%(changeInterval*2))>=changeInterval){
        DisplayConnectionInfo();
    } else{
        DisplayFingerPosition();
    }
}

void DisplayFingerPosition(){
    display.println("Servo Moters: \n");
    display.print("Thumb: ");
    display.println(Servo_Thumb.read());
    display.print("Index: ");
    display.println(Servo_Index.read());
    display.print("Middle: ");
    display.println(Servo_Middle.read());
    display.print("Ring: ");
    display.println(Servo_Ring.read());
    display.print("Pinky: ");
    display.println(Servo_Pinky.read());
    display.display();
}

void DisplayConnectionInfo(){
    display.println("Connection Info: \n");
    
    if(AP_ON){
        display.print("SSID: ");
        display.println(WiFi.softAPSSID().c_str());
        display.print("Pass: ");
        display.println(Config["SelfAP"]["password"].as<const char*>());
        display.print("IP: ");
        display.println(WiFi.softAPIP().toString().c_str());
    } else {
        display.print("SSID: ");
        display.println(WiFi.SSID().c_str());
        display.print("IP: ");
        display.println(WiFi.localIP().toString().c_str());
    }

    unsigned long ms = millis();
    display.print("Up Time: ");
    display.printf("%02lu:%02lu:%02lu", ms / 3600000, (ms / 60000) % 60, (ms / 1000) % 60);
    display.display();
}

void PopUpOLED(String text, int time=500){
    display.clearDisplay();
    display.setCursor(0,0);
    display.println(text);
    display.display();
    displayLockUpTo = millis() + 1000;
}

void setCooldown() {
    udpCooldownUntil = millis() + UDP_COOLDOWN_MS;
}

void handleServoUpdate(int thumb, int index, int middle, int ring, int pinky, bool fromHttp=false) {
    if (thumb >= 0) Servo_Thumb.write(thumb);
    if (index >= 0) Servo_Index.write(index);
    if (middle >= 0) Servo_Middle.write(middle);
    if (ring >= 0) Servo_Ring.write(ring);
    if (pinky >= 0) Servo_Pinky.write(pinky);
    gestureAnimating = false;
    if (fromHttp) setCooldown();
}

void parseServoData(String data) {
    int values[5] = {-1, -1, -1, -1, -1};
    int currentIndex = 0;
    int start = 0;
    for (int i = 0; i <= data.length(); i++) {
        if (i == data.length() || data.charAt(i) == ',') {
            String valueStr = data.substring(start, i);
            valueStr.trim();
            if (currentIndex < 5 && valueStr.length() > 0) {
                values[currentIndex] = valueStr.toInt();
            }
            currentIndex++;
            start = i + 1;
        }
    }
    handleServoUpdate(values[0], values[1], values[2], values[3], values[4]);
}

void handleUdpPacket() {
    char packetBuffer[256];
    int packetSize = udpServer.parsePacket();
    if (packetSize) {
        udpServer.read(packetBuffer, 255);
        packetBuffer[packetSize] = '\0';
        Serial.println("UDP Data: " + String(packetBuffer));
        parseServoData(String(packetBuffer));
    }
}

void startGesture(String type) {
    if (type == "open") {
        setCooldown();
        Servo_Thumb.write(0);
        Servo_Index.write(0);
        Servo_Middle.write(0);
        Servo_Ring.write(0);
        Servo_Pinky.write(0);
    } else if (type == "close" || type == "fist") {
        setCooldown();
        Servo_Thumb.write(180);
        Servo_Index.write(180);
        Servo_Middle.write(180);
        Servo_Ring.write(180);
        Servo_Pinky.write(180);
    } else if (type == "point") {
        setCooldown();
        Servo_Thumb.write(180);
        Servo_Index.write(0);
        Servo_Middle.write(180);
        Servo_Ring.write(180);
        Servo_Pinky.write(180);
    } else if (type == "yo") {
        setCooldown();
        Servo_Thumb.write(0);
        Servo_Index.write(0);
        Servo_Middle.write(180);
        Servo_Ring.write(180);
        Servo_Pinky.write(0);
    } else if (type == "wave") {
        setCooldown();
        gestureAnimating = true;
        gestureStep = 0;
        gestureAnimTimer = millis();
        Servo_Thumb.write(180);
        Servo_Index.write(180);
        Servo_Middle.write(180);
        Servo_Ring.write(180);
        Servo_Pinky.write(180);
    }
}

void updateGestureAnimation() {
    if (!gestureAnimating) return;
    if (millis() - gestureAnimTimer < WAVE_DELAY) return;
    
    gestureAnimTimer = millis();
    gestureStep++;
    
    if (gestureStep == 1) {
        Servo_Pinky.write(0);
    } else if (gestureStep == 2) {
        Servo_Ring.write(0);
    } else if (gestureStep == 3) {
        Servo_Middle.write(0);
    } else if (gestureStep == 4) {
        Servo_Index.write(0);
    } else if (gestureStep == 5) {
        Servo_Thumb.write(0);
    } else if (gestureStep == 6) {
        Servo_Thumb.write(180);
    } else if (gestureStep == 7) {
        Servo_Index.write(180);
    } else if (gestureStep == 8) {
        Servo_Middle.write(180);
    } else if (gestureStep == 9) {
        Servo_Ring.write(180);
    } else if (gestureStep == 10) {
        Servo_Pinky.write(0);
    } else {
        gestureAnimating = false;
    }
}

void handleHttpCooldown() {
    if (millis() > udpCooldownUntil) {
        udpCooldownUntil = 0;
    }
}

void WebSrvLoadRoutes(){
    webServer.on("/", []() {
        PopUpOLED("Sent Add WiFi Network Page", 100);
        webServer.send(200, "text/html", "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Add a SSID Wi-Fi</title><style>* {margin: 0;padding: 0;box-sizing: border-box;}body {font-family: Arial, sans-serif;background: #f4f4f9;display: flex;justify-content: center;align-items: center;height: 100vh;color: #333;}.form-container {background: #fff;padding: 20px;border-radius: 8px;box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);width: 100%;max-width: 400px;}h2 {text-align: center;margin-bottom: 20px;color: #444;}form label {display: block;margin-bottom: 5px;font-weight: bold;}form input {width: 100%;padding: 10px;margin-bottom: 15px;border: 1px solid #ccc;border-radius: 5px;font-size: 1rem;}form input:focus {border-color: #007bff;outline: none;}button {width: 100%;padding: 10px;color: white;border: none;border-radius: 5px;font-size: 1rem;cursor: pointer;}button.submit-button {background: #007bff;}button.submit-button:hover {background: #0056b3;}button.reboot-button {background: #ff4d4d;margin-top: 10px;}button.reboot-button:hover {background: #cc0000;}a {display: block;margin-top: 15px;text-align: center;color: #007bff;text-decoration: none;font-size: 1rem;}a:hover {text-decoration: underline;}@media (max-width: 600px) {.form-container {padding: 15px;}button {padding: 8px;}}</style></head><body><div class=\"form-container\"><form id=\"wifi-config-form\" action=\"/addNetwork\" method=\"POST\"><h2>Wi-Fi Configuration <br> Add Network</h2><label for=\"key\">Key:</label><input type=\"text\" id=\"key\" name=\"key\" placeholder=\"Enter Key\" required><label for=\"ssid\">SSID:</label><input type=\"text\" id=\"ssid\" name=\"ssid\" placeholder=\"Enter SSID\" required><label for=\"password\">Password:</label><input type=\"password\" id=\"password\" name=\"password\" placeholder=\"Enter Password\"><button type=\"submit\" class=\"submit-button\">Submit</button><button type=\"button\" class=\"reboot-button\" onclick=\"window.location.href='/reboot'\">Reboot</button></form><a href=\"/controlGUI\">Go to Control GUI</a></div></body></html>");
    });

    webServer.on("/reboot", []() {
        PopUpOLED("Rebooting...", 5000);
        webServer.send(200, "text/html", replaceSubstring("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Pop Up and redirect</title></head><body><script>alert(\"####MSGHERE####\");window.location.href = \"/\";</script></body></html>"
, "####MSGHERE####", "Restarting"));
        ESP.restart();
    });
     
    webServer.on("/controlAll", []() {
        String thumbStr = webServer.arg("thumb");
        String indexStr = webServer.arg("index");
        String middleStr = webServer.arg("middle");
        String ringStr = webServer.arg("ring");
        String pinkyStr = webServer.arg("pinky");
        Serial.println("Control All Route Hit - thumb:" + thumbStr + " index:" + indexStr + " middle:" + middleStr + " ring:" + ringStr + " pinky:" + pinkyStr);
        
        int thumb = thumbStr.length() > 0 ? thumbStr.toInt() : -1;
        int index = indexStr.length() > 0 ? indexStr.toInt() : -1;
        int middle = middleStr.length() > 0 ? middleStr.toInt() : -1;
        int ring = ringStr.length() > 0 ? ringStr.toInt() : -1;
        int pinky = pinkyStr.length() > 0 ? pinkyStr.toInt() : -1;
        
        handleServoUpdate(thumb, index, middle, ring, pinky, true);
        webServer.send(200, "text/plain", "NICE");
    });

    webServer.on("/gesture", []() {
        String type = webServer.arg("type");
        Serial.println("Gesture Route Hit: " + type);
        startGesture(type);
        webServer.send(200, "text/plain", "NICE");
    });

    webServer.on("/addNetwork", []() {
        if (webServer.method()!=HTTP_POST) {
            webServer.send(405, "text/plain", "Method Not Allowed");
        } else {
            if(webServer.arg("key")=="Servo@grip"){
                addAPtoWiFiMulti(webServer.arg("ssid"), webServer.arg("password"));
                PopUpOLED("Added WiFi Network Successfully");
                webServer.send(200, "text/html", replaceSubstring("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Pop Up and redirect</title></head><body><script>alert(\"####MSGHERE####\");window.location.href = \"/\";</script></body></html>"
                    , "####MSGHERE####", "SSID Added Successfully"));
            } else {
                PopUpOLED("Invalid Key within Request", 2000);
                webServer.send(200, "text/html", replaceSubstring("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Pop Up and redirect</title></head><body><script>alert(\"####MSGHERE####\");window.location.href = \"/\";</script></body></html>"
                    , "####MSGHERE####", "Incorrect KEY!!"));
            }
        }
    });
    
webServer.on("/controlGUI", []() {
        if (webServer.method()==HTTP_POST) {
            String mode = webServer.arg("mode");
            if (mode == "manual") {
                Servo_Thumb.write(webServer.arg("thumb").toInt());
                Servo_Index.write(webServer.arg("index").toInt());
                Servo_Middle.write(webServer.arg("middle").toInt());
                Servo_Ring.write(webServer.arg("ring").toInt());
                Servo_Pinky.write(webServer.arg("pinky").toInt());
                setCooldown();
            } else if (mode == "open" || mode == "close" || mode == "fist" || mode == "point" || mode == "yo" || mode == "wave") {
                startGesture(mode);
            }
        }
        String thumbVal = String(Servo_Thumb.read());
        String indexVal = String(Servo_Index.read());
        String middleVal = String(Servo_Middle.read());
        String ringVal = String(Servo_Ring.read());
        String pinkyVal = String(Servo_Pinky.read());
        String MsgToSnd = "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"><title>Responsive Form</title><style>body {font-family: Arial, sans-serif;margin: 0;padding: 0;display: flex;justify-content: center;align-items: center;height: 100vh;background-color: #f0f0f0;}form {background: #ffffff;padding: 20px;border-radius: 8px;box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);width: 100%;max-width: 400px;}h2 {text-align: center;margin-bottom: 20px;}label {display: block;margin-bottom: 5px;font-weight: bold;}input[type=\"range\"] {width: 100%;margin-bottom: 15px;}input[type=\"submit\"] {width: 100%;background-color: #007BFF;color: white;padding: 10px;border: none;border-radius: 4px;cursor: pointer;font-size: 16px;}input[type=\"submit\"]:hover {background-color: #0056b3;}select {width: 100%;padding: 10px;margin-bottom: 15px;border: 1px solid #ccc;border-radius: 5px;font-size: 1rem;}#sliderSection {display: block;}#sliderSection.hidden {display: none;}</style><script>function toggleSliders(){var mode=document.getElementById('modeSelect').value;document.getElementById('sliderSection').className=mode==='manual'?'':'hidden';}</script></head><body><form id=\"valueForm\" method=\"post\" action=\"/controlGUI\"><h2>Enter Finger Values</h2><label for=\"mode\">Mode:</label><select id=\"modeSelect\" name=\"mode\" onchange=\"toggleSliders()\"><option value=\"manual\">Manual</option><option value=\"open\">Open</option><option value=\"close\">Close</option><option value=\"fist\">Fist</option><option value=\"point\">Point</option><option value=\"yo\">Yo</option><option value=\"wave\">Wave</option></select><div id=\"sliderSection\"><label for=\"thumb\">Thumb (0-180):</label><input type=\"range\" id=\"thumb\" name=\"thumb\" min=\"0\" max=\"180\" value=\"TVAL\" oninput=\"this.nextElementSibling.value = this.value\"><output class=\"out\">TVAL</output><label for=\"index\">Index (0-180):</label><input type=\"range\" id=\"index\" name=\"index\" min=\"0\" max=\"180\" value=\"IVAL\" oninput=\"this.nextElementSibling.value = this.value\"><output class=\"out\">IVAL</output><label for=\"middle\">Middle (0-180):</label><input type=\"range\" id=\"middle\" name=\"middle\" min=\"0\" max=\"180\" value=\"MVAL\" oninput=\"this.nextElementSibling.value = this.value\"><output class=\"out\">MVAL</output><label for=\"ring\">Ring (0-180):</label><input type=\"range\" id=\"ring\" name=\"ring\" min=\"0\" max=\"180\" value=\"RVAL\" oninput=\"this.nextElementSibling.value = this.value\"><output class=\"out\">RVAL</output><label for=\"pinky\">Pinky (0-180):</label><input type=\"range\" id=\"pinky\" name=\"pinky\" min=\"0\" max=\"180\" value=\"PVAL\" oninput=\"this.nextElementSibling.value = this.value\"><output class=\"out\">PVAL</output></div><button type=\"submit\">Apply</button></form></body></html>";
        MsgToSnd.replace("TVAL", thumbVal);
        MsgToSnd.replace("IVAL", indexVal);
        MsgToSnd.replace("MVAL", middleVal);
        MsgToSnd.replace("RVAL", ringVal);
        MsgToSnd.replace("PVAL", pinkyVal);
        webServer.send(200, "text/html", MsgToSnd);
        PopUpOLED("Sent Control GUI Page", 100);
    });

    webServer.onNotFound([]() {
        webServer.send(200, "text/html", "<script>window.location.href='/'</script>");
    });
}

void createAPandRedirectToConfig(){
    AP_ON = true;
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAPConfig(IPAddress(192,168,2,1), IPAddress(192,168,2,1), IPAddress(255,255,255,0))) {
        Serial.println("Failed to configure Access Point");
    }
    if (!WiFi.softAP(Config["SelfAP"]["ssid"].as<const char*>(), Config["SelfAP"]["password"].as<const char*>())) {
        Serial.println("Failed to start Access Point");
    }
    //WiFi.softAPDhcpServer().begin();
}


void setup() {
    Serial.begin(74880);
    if (!SPIFFS.begin()) {Serial.println("Failed to mount SPIFFS");} // Init File System
    
    //Servo Setup
    Servo_Thumb.attach(D0, 500, 2400);
    Servo_Index.attach(D3, 500, 2400);
    Servo_Middle.attach(D5, 500, 2400);
    Servo_Ring.attach(D6, 500, 2400);
    Servo_Pinky.attach(D7, 500, 2400);

    Servo_Thumb.write(0);
    Servo_Index.write(0);
    Servo_Middle.write(0);
    Servo_Ring.write(0);
    Servo_Pinky.write(0);
    
    // Setting up display
    // Wire.begin(Config["OLED_SDA"], Config["OLED_SCL"]);
    if (!display.begin(0x3C)) {
        Serial.println(F("Failed to initialize the display!"));
    }
    display.display();
    display.setTextColor(SH110X_WHITE);
    display.setTextSize(1);
    //Get Config and set up WiFi
    WiFi.mode(WIFI_STA);
	getConfig();
    if(Config["WifiMulti"].size()>0){
        for (int x=0; x<Config["WifiMulti"].size(); x++) {
            wifiMulti.addAP(Config["WifiMulti"][x][0].as<const char*>(), Config["WifiMulti"][x][1].as<const char*>());
        }
        int WifiMultiTrials = 0;
        while ((wifiMulti.run() != WL_CONNECTED) && (WifiMultiTrials < 3)) {
            WifiMultiTrials++;
            WiFiMultiConnectingLoading();
        }
        if (WiFi.isConnected()) {
            PopUpOLED("WiFi Connection Success");
            Serial.printf("Wifi connected to: %s\n", WiFi.SSID().c_str());
            Serial.printf("IP: %s\n", WiFi.localIP().toString().c_str());
        } else {
            Serial.printf("Connecting to wifi failed, configure it in web portal\n");
            PopUpOLED("Connection Failed");
            createAPandRedirectToConfig();
        }
    } else {
        Serial.println("No Wifi Networks listed. Starting AP");
        PopUpOLED("No Wifi Networks listed. Starting AP");
        createAPandRedirectToConfig();
    }

    //Start MDNS Responder
    if (!MDNS.begin("esp8266")) {
        Serial.println("Error setting up MDNS responder!");
    }

    if (AP_ON) {
        // DNS Setup
        dnsServer.setTTL(300);
        dnsServer.setErrorReplyCode(DNSReplyCode::ServerFailure);
        dnsServer.start(53, "*", WiFi.softAPIP());
    }

    //WebServer Setup
    WebSrvLoadRoutes();
    webServer.begin();

    //UDP Setup
    udpServer.begin(UDP_PORT);
    Serial.printf("UDP Server started on port %d\n", UDP_PORT);
}

void loop() {
    handleHttpCooldown();
    if (millis() > udpCooldownUntil || udpCooldownUntil == 0) {
        handleUdpPacket();
    }
    updateGestureAnimation();
    webServer.handleClient();
    MDNS.update();
    UpdateOLED();
    if (AP_ON) {
        dnsServer.processNextRequest();
    } else if (!WiFi.isConnected()){
        PopUpOLED("WiFi Disconnected\nStarting Access Point");
        createAPandRedirectToConfig();
    }
}
