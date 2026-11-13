/*
	MQ7.h - Versi Kustom untuk ESP32 & Arduino
	Diadaptasi dari library asli karya Fergus Baker (2020)
	Disesuaikan untuk proyek: AIoT Klasifikasi Udara (ESP32)
*/

#ifndef MQ7_H
#define MQ7_H

#include <Arduino.h>

/*
	PILIHAN KONFIGURASI
*/
#define CALIBRATION_SECONDS 15
#define _R0 20.1000	// Hapus komentar ini jika ingin mengunci nilai R0 (tidak perlu delay 15 detik tiap startup)

// Deteksi otomatis resolusi ADC mikrokontroler:
// ESP32 menggunakan ADC bawaan 12-bit (0 - 4095.0)
// Arduino Uno/Nano menggunakan ADC 10-bit (0 - 1023.0)
#if defined(ESP32)
  #define _ADC_RESOLUTION 4095.0
#elif defined(ESP8266)
  #define _ADC_RESOLUTION 1023.0
#else
  #define _ADC_RESOLUTION 1023.0
#endif

// Parameter fitting kurva sensitivitas datasheet MQ-7:
// ppm(Rs/R0) = A0 * (Rs/R0) ^ A1
#define _COEF_A0 100.0
#define _COEF_A1 -1.513

// Load resistance (RL) tipikal pada modul breakout MQ-7 (~10 kOhm)
#define _LOAD_RES 10.0

// Pada udara bersih (clean air), rasio Rs/R0 menurut datasheet adalah ~5.0
#define _CALIBRATION_CONSTANT 5.0

class MQ7 {
public:
	MQ7(int pin) : a_pin(pin), v_in(5.0) { 
		#ifndef _R0
		R0 = 1.0;
		#endif
	}

	MQ7(int pin, float v_in) : a_pin(pin), v_in(v_in) {
		#ifndef _R0
		R0 = 1.0;
		#endif
	}

	// Membaca konsentrasi gas CO bersih dalam PPM (0.0 PPM di udara bersih, naik proporsional saat ada asap/CO)
	float readPpm();

	// Membaca konsentrasi gas CO mentah absolut berdasarkan kurva kurva daya datasheet (termasuk offset baseline ~8.8 PPM)
	float readRawPpm();

	// Membaca resistansi sensor Rs (dalam kOhm)
	float readRs();

	// Membaca rasio Rs/RL
	float readRsRL();

	// Melakukan proses kalibrasi rata-rata selama 15 detik di udara bersih
	void calibrate();

	// Mengambil nilai R0 yang tersimpan saat ini
	float getR0();

	// Mengatur nilai R0 secara manual dari kodingan sketch
	void setR0(float r0);

private:
	int a_pin;
	float v_in;

	#ifndef _R0
	float R0;
	#else
	const float R0 = _R0;
	#endif

	float convertVoltage(int raw);
};

#endif
