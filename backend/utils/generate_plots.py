import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.neighbors import KNeighborsClassifier
import matplotlib.pyplot as plt

# Tentukan path file dataset
excel_path = 'c:/Users/Victus/Documents/AIoT-Klasifikasi-Udara/docs/CONFINED_SPACE_CLASSIFIED.xlsx'

# Membaca file Excel tanpa header default
df_raw = pd.read_excel(excel_path, header=None)

# Bersihkan data dan tentukan kolom baru
data_rows = df_raw.iloc[2:].copy()
data_rows.columns = [
    'vessel_ship', 'location_work', 'date', 'session', 'time',
    'o2', 'o2_desc', 'co', 'co_desc', 'air_quality',
    'o2_class_computed', 'co_class_computed', 'col12', 'col13'
]

# Pilih kolom O2, CO, dan Kelas Target
df = data_rows[['o2', 'co', 'air_quality']].copy()

# Bersihkan baris kosong atau tidak valid
df = df.dropna(subset=['o2', 'co', 'air_quality'])
df['o2'] = pd.to_numeric(df['o2'], errors='coerce')
df['co'] = pd.to_numeric(df['co'], errors='coerce')
df = df.dropna()

# Format label kelas agar konsisten
df['air_quality'] = df['air_quality'].astype(str).str.strip().str.capitalize()

# Pisahkan fitur (X) dan label kelas (y) dari data asli (Tanpa Synthetic Data)
X = df[['o2', 'co']].values
y = df['air_quality'].values

# Fit dan transform fitur menggunakan MinMaxScaler
scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X)

# Pembagian dataset (80% training dan 20% testing)
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=42, stratify=y
)

def plot_knn_prediction(model, X_train_original, y_train, test_point, k, filename):
    """
    Fungsi untuk memvisualisasikan K-Nearest Neighbors dari suatu data uji
    """
    # Prediksi kelas
    test_scaled = scaler.transform([test_point])
    pred_class = model.predict(test_scaled)[0]
    
    # Cari tetangga terdekat (diperlukan pencarian pada data latih)
    distances, indices = model.kneighbors(test_scaled)
    nearest_neighbors_idx = indices[0]
    
    plt.figure(figsize=(9, 6))
    
    # Plot Data Latih (X_train_original) - kita harus melakukan inverse transform jika mau plotting di skala asli
    # Atau lebih baik, kita cari tetangga di skala scaling, lalu plot di skala asli
    
    # Supaya mudah, kita plot beberapa sampel di sekitar data latih
    # Pertama, ambil K data terdekat dari X_train_original
    X_train_orig = scaler.inverse_transform(X_train)
    nearest_points = X_train_orig[nearest_neighbors_idx]
    nearest_labels = y_train[nearest_neighbors_idx]
    
    # Plot data uji
    plt.scatter(test_point[1], test_point[0], c='black', marker='X', s=200, label='Data Uji', zorder=5)
    
    # Plot titik-titik tetangga terdekat
    colors = {'Safe': 'green', 'Aware': 'orange', 'Danger': 'red'}
    for i, (point, label) in enumerate(zip(nearest_points, nearest_labels)):
        plt.scatter(point[1], point[0], c=colors[label], s=100, label=label if i == 0 else "")
        # Garis penghubung
        plt.plot([test_point[1], point[1]], [test_point[0], point[0]], 'k--', zorder=4)
        plt.text(point[1]+0.2, point[0]+0.01, f"{label}", fontsize=9)
        
    # Tambahkan beberapa titik lain sebagai background (opsional, untuk konteks)
    # Ambil sampel acak dari dataset asli
    np.random.seed(42) # fix seed for consistent background points
    sample_indices = np.random.choice(len(X_train_orig), min(50, len(X_train_orig)), replace=False)
    for idx in sample_indices:
        if idx not in nearest_neighbors_idx:
            pt = X_train_orig[idx]
            lbl = y_train[idx]
            plt.scatter(pt[1], pt[0], c=colors[lbl], s=50, alpha=0.3)
    
    plt.xlabel('Kadar CO (ppm)')
    plt.ylabel('Kadar O$_2$ (%)')
    plt.title(f'Visualisasi Algoritma K-Nearest Neighbor (K = {k})')
    
    # Filter legend agar tidak duplikat
    handles, labels = plt.gca().get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    
    # Urutkan legend: Data Uji, Safe, Aware, Danger (jika ada)
    # Hapus item kosong (jika ada)
    if '' in by_label: del by_label['']
    
    plt.legend(by_label.values(), by_label.keys())
    plt.grid(True)
    plt.savefig(filename, bbox_inches='tight')
    plt.close()

# test data: O2 = 20.3, CO = 12
test_data = [20.3, 26]

# K=5
knn_k5 = KNeighborsClassifier(n_neighbors=5, metric='euclidean')
knn_k5.fit(X_train, y_train)
plot_knn_prediction(knn_k5, X_train, y_train, test_data, k=5, filename='knn_k5.png')

# K=15
knn_k15 = KNeighborsClassifier(n_neighbors=15, metric='euclidean')
knn_k15.fit(X_train, y_train)
plot_knn_prediction(knn_k15, X_train, y_train, test_data, k=15, filename='knn_k15.png')
