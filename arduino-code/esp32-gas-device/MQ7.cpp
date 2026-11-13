/*
	MQ7.cpp - Versi Kustom untuk ESP32 & Arduino
	Diadaptasi dari library asli karya Fergus Baker (2020)
	Disesuaikan untuk proyek: AIoT Klasifikasi Udara (ESP32)
*/

#include "MQ7.h"
#include <Arduino.h>

// Pre-calculated konstanta cleanAirBaseline di udara bersih kalibrasi (Rs/R0 = 5.0)
// cleanAirBaseline = 100.0f * powf(5.0f, -1.513f) ≈ 8.7828f
static const float CLEAN_AIR_BASELINE = 8.7828f;

float MQ7::readRawPpm() {
	if (R0 <= 0.0001f) {
		return 0.0f;
	}

	float ratio = readRs() / R0;
	if (ratio <= 0.0001f) {
		return 0.0f;
	}

	// Formula fitting datasheet MQ-7: ppm = A0 * (Rs/R0) ^ A1
	// Gunakan powf() agar langsung diproses oleh hardware FPU ESP32 secara instan
	return (float) _COEF_A0 * powf(ratio, (float)_COEF_A1);
}

float MQ7::readPpm() {
	float raw = readRawPpm();

	// Kurangkan baseline menggunakan konstanta pra-hitung (zero runtime computation overhead)
	// sehingga di udara bersih murni menghasilkan 0.0 PPM,
	// dan mulai naik secara proporsional dan akurat saat ada gas CO / asap
	float netPpm = raw - CLEAN_AIR_BASELINE;
	if (netPpm < 0.0f) {
		netPpm = 0.0f;
	}

	return netPpm;
}

float MQ7::readRs() {
	return _LOAD_RES * readRsRL();
}

float MQ7::readRsRL() {
	int raw = analogRead(a_pin);
	float voltage = convertVoltage(raw);

	// Clamping pengaman:
	// Mencegah pembagian dengan nol atau nilai tegangan melebihi v_in
	// yang dapat menghasilkan bilangan negatif dan memicu nilai NaN pada fungsi pow()
	if (voltage <= 0.001f) {
		voltage = 0.001f;
	}
	if (voltage >= v_in) {
		voltage = v_in - 0.001f;
	}

	return (v_in - voltage) / voltage;
}

float MQ7::convertVoltage(int raw) {
	// Konversi nilai ADC mikrokontroler ke tegangan (ESP32: 0 - 4095.0)
	return (float) raw * (v_in / _ADC_RESOLUTION);
}

void MQ7::calibrate() {
	#ifndef _R0	// Hanya lakukan jika nilai R0 tidak di-hardcode

	float sumRs = 0.0f;
	for (int i = 0; i < CALIBRATION_SECONDS; i++) {
		delay(1000);
		sumRs += readRs();
	}
	
	// Menghitung rata-rata akumulasi pembacaan selama 15 detik
	// agar hasil kalibrasi stabil dari noise / fluktuasi sesaat
	R0 = (sumRs / (float)CALIBRATION_SECONDS) / _CALIBRATION_CONSTANT;

	#endif
}

float MQ7::getR0() {
	return R0;
}

void MQ7::setR0(float r0) {
	#ifndef _R0
	if (r0 > 0.0001f) {
		R0 = r0;
	}
	#endif
}
