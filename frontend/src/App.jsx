import React, { useState, useEffect } from 'react';
import Chart from 'react-apexcharts';
import GaugeComponent from 'react-gauge-component';
import { Download } from 'lucide-react';
import './App.css';

function App() {

  // --------------------------------------------------------------------------
  // 1. STATE MANAGEMENT (VARIABEL STATUS)
  // --------------------------------------------------------------------------

  // Menyimpan data sensor real-time terbaru yang diterima (O2, CO, Vessel, dll)
  const [data, setData] = useState(null);

  // Menyimpan data koordinat tren historis untuk disajikan ke dalam ApexCharts
  const [history, setHistory] = useState({ o2: [], co: [], labels: [] });

  // Menyimpan daftar log historis terakhir (50 data terbaru) untuk tabel bawah
  const [logs, setLogs] = useState([]);

  // Status koneksi WebSocket ("connecting", "connected", atau "disconnected")
  const [connectionStatus, setConnectionStatus] = useState("connecting");

  // Status apakah backend tersambung ke Broker MQTT (True/False)
  const [mqttConnected, setMqttConnected] = useState(false);


  const [deviceActive, setDeviceActive] = useState(false);

  // Status pop-up modal unduh laporan
  const [showModal, setShowModal] = useState(false);
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");

  // --------------------------------------------------------------------------
  // 2. API CALLS & WEBSOCKET SYNC (FUNGSI SYNC DATA)
  // --------------------------------------------------------------------------

  /**
   * Mengambil log data riil terakhir dari database SQLite melalui API REST.
   * Dipanggil saat mount awal dasbor.
   */
  const fetchLogs = () => {
    fetch('http://localhost:8000/api/logs')
      .then(res => res.json())
      .then(data => {
        setLogs(data);

        // Menginisialisasi grafik tren menggunakan log riil di database.
        // Dibalik (reverse) agar kronologinya urut dari data terlama ke terbaru.
        const reversedLogs = [...data].reverse();
        const o2History = reversedLogs.map(log => log.o2);
        const coHistory = reversedLogs.map(log => log.co);
        const labelsHistory = reversedLogs.map(log =>
          new Date(log.timestamp).toLocaleTimeString('en-US', { hour12: false })
        );

        // Membatasi hanya menampilkan 15 titik koordinat terakhir pada grafik
        setHistory({
          o2: o2History.slice(-15),
          co: coHistory.slice(-15),
          labels: labelsHistory.slice(-15)
        });
      })
      .catch(err => console.error("Failed to fetch logs:", err));
  };

  /**
   * Effect Hook untuk membuka koneksi WebSocket dan mendengarkan data real-time.
   */
  useEffect(() => {
    fetchLogs();

    let ws;
    const connectWS = () => {
      ws = new WebSocket('ws://localhost:8000/ws/air-quality');

      ws.onopen = () => {
        setConnectionStatus("connected");
        console.log("WebSocket connected.");
      };

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);

        if (message.type === 'status') {
          setMqttConnected(message.mqtt_connected);
          setDeviceActive(message.device_active);

          if (message.latest_data) {
            const payload = message.latest_data;
            setData(payload);

            const timestamp = new Date(payload.timestamp).toLocaleTimeString('en-US', { hour12: false });

            setHistory(prev => {
              if (prev.labels.includes(timestamp)) return prev;
              return {
                o2: [...prev.o2.slice(-14), payload.o2],
                co: [...prev.co.slice(-14), payload.co],
                labels: [...prev.labels.slice(-14), timestamp]
              };
            });

            setLogs(prev => {
              if (prev.some(l => l.timestamp === payload.timestamp)) return prev;
              return [payload, ...prev.slice(0, 49)];
            });
          }
        }
      };

      ws.onclose = () => {
        setConnectionStatus("disconnected");
        console.log("WebSocket disconnected. Retrying in 3s...");
        setTimeout(connectWS, 3000);
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
      };
    };

    connectWS();

    return () => {
      if (ws) ws.close();
    };
  }, []);

  /**
   * Mengirim permintaan unduh ke backend untuk mengekspor data logs
   * berdasarkan filter rentang tanggal & waktu ke berkas Excel.
   */
  const handleDownloadExcel = async () => {
    try {
      let url = 'http://localhost:8000/api/logs/download';
      const params = [];

      // Mengonversi tanggal input lokal ke format UTC ISOString agar cocok dengan basis data
      if (startTime) {
        const dateObj = new Date(startTime);
        if (!isNaN(dateObj.getTime())) {
          params.push(`start_time=${encodeURIComponent(dateObj.toISOString())}`);
        }
      }
      if (endTime) {
        const dateObj = new Date(endTime);
        if (!isNaN(dateObj.getTime())) {
          params.push(`end_time=${encodeURIComponent(dateObj.toISOString())}`);
        }
      }

      // Mengirimkan offset zona waktu browser agar jam di file Excel tetap sesuai waktu lokal user
      const offset = new Date().getTimezoneOffset();
      params.push(`timezone_offset=${offset}`);

      if (params.length > 0) {
        url += `?${params.join('&')}`;
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error("Gagal mengunduh laporan excel dari server.");
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);

      // Mengekstrak nama berkas yang dikirimkan oleh backend header
      const contentDisposition = response.headers.get('content-disposition');
      let filename = "Laporan_Kualitas_Udara.xlsx";
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="(.+?)"/);
        if (match && match[1]) {
          filename = match[1];
        }
      }

      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);

      // Tutup modal popup setelah sukses
      setShowModal(false);
    } catch (err) {
      alert("Kesalahan saat mengunduh laporan: " + err.message);
    }
  };

  // --------------------------------------------------------------------------
  // 3. UI STYLE RESOLVERS (FUNGSI BANTU GAYA KARTU STATUS)
  // --------------------------------------------------------------------------

  const getStatusColor = (status) => {
    if (status === 'Safe') return 'var(--color-safe-text)';
    if (status === 'Aware') return 'var(--color-aware-text)';
    return 'var(--color-danger-text)';
  };

  const getStatusClass = (status) => {
    if (status === 'Safe') return 'card-status-safe';
    if (status === 'Aware') return 'card-status-aware';
    return 'card-status-danger';
  };

  const getStatusDesc = (status) => {
    if (status === 'Safe') return '✓ Kondisi Aman';
    if (status === 'Aware') return '⚠ Perlu Perhatian';
    return '✖ Bahaya Kritis!';
  };

  // --------------------------------------------------------------------------
  // 4. CHART OPTIONS (KONFIGURASI GRAFIK TREN APEXCHARTS - LIGHT THEME)
  // --------------------------------------------------------------------------

  const coChartOptions = {
    chart: {
      id: 'co-trend-chart',
      type: 'line',
      background: '#ffffff',
      toolbar: { show: false }
    },
    theme: { mode: 'light' },
    xaxis: {
      categories: history.labels,
      tickAmount: 5,
      labels: {
        rotate: -30,
        style: { colors: '#475569', fontWeight: 600, fontSize: '10px' }
      }
    },
    yaxis: {
      labels: { style: { colors: '#475569', fontWeight: 600 } }
    },
    colors: ['#0f3057'],
    stroke: { curve: 'smooth', width: 3 },
    grid: { borderColor: '#e2e8f0' },
    markers: {
      size: 4,
      colors: ['#0f3057'],
      strokeColors: '#ffffff',
      strokeWidth: 1.5,
      hover: { size: 6 }
    },
    tooltip: {
      y: {
        formatter: (val) => `${val.toFixed(1)} ppm`
      }
    },
    annotations: {
      yaxis: [
        {
          y: 9,
          borderColor: '#d97706',
          borderWidth: 1.5,
          label: {
            borderColor: '#d97706',
            style: { color: '#fff', background: '#d97706', fontWeight: 'bold' },
            text: 'Batas Aware (9ppm)'
          }
        }
      ]
    }
  };

  const o2ChartOptions = {
    chart: {
      id: 'o2-trend-chart',
      type: 'line',
      background: '#ffffff',
      toolbar: { show: false }
    },
    theme: { mode: 'light' },
    xaxis: {
      categories: history.labels,
      tickAmount: 5,
      labels: {
        rotate: -30,
        style: { colors: '#475569', fontWeight: 600, fontSize: '10px' }
      }
    },
    yaxis: {
      labels: { style: { colors: '#475569', fontWeight: 600 } }
    },
    colors: ['#16a34a'],
    stroke: { curve: 'smooth', width: 3 },
    grid: { borderColor: '#e2e8f0' },
    markers: {
      size: 4,
      colors: ['#16a34a'],
      strokeColors: '#ffffff',
      strokeWidth: 1.5,
      hover: { size: 6 }
    },
    tooltip: {
      y: {
        formatter: (val) => `${val.toFixed(2)} %`
      }
    }
  };

  const coSeries = [{ name: 'CO (ppm)', data: history.co }];
  const o2Series = [{ name: 'O2 (%)', data: history.o2 }];

  const getFormattedTime = () => {
    if (data) {
      return new Date(data.timestamp).toLocaleTimeString('en-US', { hour12: false });
    }
    return new Date().toLocaleTimeString('en-US', { hour12: false });
  };

  const getFormattedDate = () => {
    if (data) {
      return new Date(data.timestamp).toLocaleDateString('en-GB');
    }
    return new Date().toLocaleDateString('en-GB');
  };

  // --------------------------------------------------------------------------
  // 5. COMPONENT LAYOUT RENDERING (STRUKTUR PANEL TAMPILAN)
  // --------------------------------------------------------------------------

  return (
    <div className="dashboard-wrapper">

      {/* HEADER UTAMA DASBOR (GAYA MONITOR RUANG KONTROL KAPAL) */}
      <header className="header-bar">
        <div className="header-title">
          <span>Air Quality Monitor - Engine Room</span>
        </div>
        <div className="header-status">
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: (connectionStatus === "connected" && deviceActive) ? "#10b981" : "#ef4444",
              display: 'inline-block'
            }}></span>
            <span style={{ fontSize: '0.85rem', fontWeight: 'bold' }}>
              {(connectionStatus === "connected" && deviceActive) ? "ONLINE" : "OFFLINE"}
            </span>
          </div>
          <span>|</span>
          <span style={{ fontSize: '0.85rem', fontWeight: '500' }}>
            {getFormattedTime()}
          </span>
        </div>
      </header>

      {/* BARIS ATAS: 4 KARTU SOLID STATUS & DIAL GAUGES */}
      <div className="top-row-grid">

        {/* KARTU 1: STATUS KLASIFIKASI KUALITAS UDARA (KNN OUTPUT) */}
        <div className={`mock-card ${data ? getStatusClass(data.knn_class) : 'card-status-safe'}`}>
          <span className="card-label">Status Kualitas Udara</span>
          <div className="card-value-big">
            {data ? data.knn_class.toUpperCase() : 'SAFE'}
          </div>
          <span className="card-desc">
            {data ? getStatusDesc(data.knn_class) : '✓ Kondisi Aman'}
          </span>
        </div>

        {/* KARTU 2: KADAR GAS CO (DENGAN WIDGET DIAL GAUGE) */}
        <div className="mock-card card-co">
          <span className="card-label">Kadar CO</span>
          <div className="gauge-wrapper">
            <GaugeComponent
              type="semicircle"
              value={data ? data.co : 0}
              minValue={0}
              maxValue={50}
              marginInPercent={{ top: 0.05, bottom: 0.00, left: 0.05, right: 0.05 }}
              pointer={{
                type: "needle",
                color: "#475569",
                length: 0.75,
                width: 10
              }}
              labels={{
                valueLabel: {
                  style: { fill: '#0f172a', textShadow: 'none', fontSize: 'var(--gauge-font-size, 24px)', fontWeight: '800', fontFamily: 'Inter, sans-serif' },
                  offsetY: 25
                },
                tickLabels: {
                  hideMinMax: true,
                  defaultTickValueConfig: { hide: true },
                  defaultTickLineConfig: { hide: true }
                }
              }}
              arc={{
                width: 0.16,
                padding: 0.02,
                subArcs: [
                  { limit: 9, color: "#10b981" }, // Safe (Green)
                  { limit: 20, color: "#f59e0b" }, // Aware (Orange)
                  { limit: 50, color: "#ef4444" }  // Danger (Red)
                ]
              }}
            />
          </div>
          <span className="card-desc">Batas Aman: &lt; 9 ppm</span>
        </div>

        {/* KARTU 3: KADAR GAS O2 (DENGAN WIDGET DIAL GAUGE) */}
        <div className="mock-card card-o2">
          <span className="card-label">Kadar O₂</span>
          <div className="gauge-wrapper">
            <GaugeComponent
              type="semicircle"
              value={data ? data.o2 : 20.9}
              minValue={15}
              maxValue={25}
              marginInPercent={{ top: 0.05, bottom: 0.00, left: 0.05, right: 0.05 }}
              pointer={{
                type: "needle",
                color: "#475569",
                length: 0.75,
                width: 10
              }}
              labels={{
                valueLabel: {
                  style: { fill: '#0f172a', textShadow: 'none', fontSize: 'var(--gauge-font-size, 24px)', fontWeight: '800', fontFamily: 'Inter, sans-serif' },
                  offsetY: 25
                },
                tickLabels: {
                  hideMinMax: true,
                  defaultTickValueConfig: { hide: true },
                  defaultTickLineConfig: { hide: true }
                }
              }}
              arc={{
                width: 0.16,
                padding: 0.02,
                subArcs: [
                  { limit: 19.5, color: "#ef4444" }, // Danger (Red)
                  { limit: 20.8, color: "#f59e0b" }, // Aware (Orange)
                  { limit: 25, color: "#10b981" }    // Safe (Green)
                ]
              }}
            />
          </div>
          <span className="card-desc">Normal: &ge; 20.8%</span>
        </div>

        <div className="mock-card card-update">
          <span className="card-label">Update</span>
          <div className="card-value-big">
            {getFormattedTime()}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', alignItems: 'center' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: '500' }}>{getFormattedDate()}</span>
            <span style={{ 
              fontSize: '0.75rem', 
              marginTop: '4px', 
              fontWeight: '500', 
              color: deviceActive ? '#10B981' : '#EF4444' 
            }}>
              ESP32 {deviceActive ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
      </div>

      {/* BARIS TENGAH: DUA GRAFIK TREN CO & O2 BERDAMPINGAN */}
      <div className="charts-grid">

        {/* GRAFIK 1: TREN GAS CO */}
        <section className="glass-card">
          <div className="card-title-header">
            <h4>Tren Kadar CO (ppm) - 10 Menit Terakhir</h4>
          </div>
          <div className="chart-wrapper">
            <Chart options={coChartOptions} series={coSeries} type="line" height="100%" />
          </div>
        </section>

        {/* GRAFIK 2: TREN GAS O2 */}
        <section className="glass-card">
          <div className="card-title-header">
            <h4>Tren Kadar O₂ (%) - 10 Menit Terakhir</h4>
          </div>
          <div className="chart-wrapper">
            <Chart options={o2ChartOptions} series={o2Series} type="line" height="100%" />
          </div>
        </section>
      </div>

      {/* BARIS BAWAH: LOGS DATA TERBARU DENGAN TOMBOL ACTION POPUP */}
      <div className="logs-container">
        <div className="logs-header-row">
          <h4>Log Data Terbaru</h4>
          <div>
            <button className="action-button action-button-primary" onClick={() => setShowModal(true)}>
              <Download size={13} />
              Download Logs
            </button>
          </div>
        </div>

        <div className="log-table-wrapper">
          <table className="log-table">
            <thead>
              <tr>
                <th>Waktu</th>
                <th>CO (ppm)</th>
                <th>O₂ (%)</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '20px' }}>
                    Belum ada data log. Silakan hubungkan sensor.
                  </td>
                </tr>
              ) : (
                logs.map((log, idx) => (
                  <tr key={idx}>
                    <td>{new Date(log.timestamp).toLocaleTimeString('en-US', { hour12: false })}</td>
                    <td style={{ fontWeight: '600' }}>{log.co.toFixed(1)}</td>
                    <td style={{ fontWeight: '600' }}>{log.o2.toFixed(1)}</td>
                    <td style={{ color: getStatusColor(log.knn_class), fontWeight: 'bold' }}>
                      {log.knn_class.toUpperCase()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ====================================================================
         POP-UP MODAL: FILTER LOGS & UNDUH LAPORAN EXCEL
         ==================================================================== */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">Unduh Laporan Excel</h3>
            <p className="modal-subtitle">
              Saring riwayat perekaman kualitas udara di Engine Room berdasarkan rentang tanggal dan waktu yang diinginkan.
            </p>

            <div className="modal-form-group">
              <label>Waktu Mulai (Start Time)</label>
              <input
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>

            <div className="modal-form-group">
              <label>Waktu Selesai (End Time)</label>
              <input
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
              />
            </div>

            <div className="modal-actions">
              <button className="action-button" onClick={() => setShowModal(false)}>
                Batal
              </button>
              <button className="action-button action-button-primary" onClick={handleDownloadExcel}>
                Unduh Laporan
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
