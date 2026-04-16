#include <Arduino.h>
#include <AccelStepper.h>

AccelStepper stepper1(AccelStepper::DRIVER, 2, 3);
AccelStepper stepper2(AccelStepper::DRIVER, 4, 5);

const int en1 = 6;
const int en2 = 7;
const long STEPS_PER_REVOLUTION = 1600; //800
const float AZ_GEAR_RATIO = 75.0;
const float EL_GEAR_RATIO = 40.0;
const float MAX_AZ = 180.0;

float fi = 0.0;
float el_fi = 0.0;
bool waiting_ack = false;
String buffer = "";

void setup()
{
    Serial.begin(115200);
    pinMode(en1, OUTPUT);
    pinMode(en2, OUTPUT);
    digitalWrite(en1, HIGH);
    digitalWrite(en2, HIGH);
    stepper1.setMaxSpeed(8000);
    stepper1.setAcceleration(16000);
    stepper2.setMaxSpeed(8000);
    stepper2.setAcceleration(200000);
}

void readSerial()
{
    while (Serial.available())
    {
        char c = Serial.read();
        if (c == '\n')
        {
            buffer.trim();
            int spaceIndex = buffer.indexOf(' ');
            if (spaceIndex > 0)
            {
                float alpha = buffer.substring(0, spaceIndex).toFloat();
                float el = buffer.substring(spaceIndex + 1).toFloat();

                alpha = fmod(alpha, 360.0);
                if (alpha < 0) alpha += 360.0;
                if (alpha > MAX_AZ)
                    alpha = alpha - 360.0;

                float delta = alpha - fi;
                float el_delta = el - el_fi;

                long azSteps = -((delta / 360.0) * STEPS_PER_REVOLUTION * AZ_GEAR_RATIO);
                long elSteps = (el_delta / 360.0) * STEPS_PER_REVOLUTION * EL_GEAR_RATIO;

                if (fabs(delta) > 170.0)
                {
                    stepper1.setMaxSpeed(50000);
                    stepper1.setAcceleration(999999);
                }
                else
                {
                    stepper1.setMaxSpeed(10000);
                    stepper1.setAcceleration(8000);
                }

                fi = alpha;
                el_fi = el;
                waiting_ack = true;

                digitalWrite(en1, LOW);
                digitalWrite(en2, LOW);
                stepper1.move(azSteps);
                stepper2.move(elSteps);

                Serial.print("Moving to: ");
                Serial.print(alpha);
                Serial.print(" el: ");
                Serial.println(el);
            }
            buffer = "";
        }
        else
        {
            buffer += c;
        }
    }
}

void loop()
{
    readSerial();
    if (!stepper1.isRunning())
        digitalWrite(en1, HIGH);
    if (!stepper2.isRunning())
        digitalWrite(en2, HIGH);
    stepper1.run();
    stepper2.run();

    if (!stepper1.isRunning() && !stepper2.isRunning() && waiting_ack)
    {
        Serial.println("OK");
        waiting_ack = false;
    }
}