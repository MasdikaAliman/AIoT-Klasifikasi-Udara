#include "DFRobot_OxygenSensor.h"
#include "MQ7.h"

#define RELAY_BUZZER 15
#define RELAY_GREEN 2
#define MQ7_ANALOG 34
#define VOLTAGE 3.3

#define BUTTON_RESET 4

#define Oxygen_IICAddress ADDRESS_3
#define COLLECT_NUMBER 10  // collect number, the collection range is 1-100.