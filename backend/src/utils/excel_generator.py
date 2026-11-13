import io
import pandas as pd
from datetime import timedelta
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def generate_styled_excel(logs, timezone_offset: int, start_dt=None, end_dt=None):
    """
    Menggenerate file Excel dari daftar log kualitas udara.
    """
    # Hitung offset untuk penyesuaian zona waktu lokal pengguna
    local_offset = timedelta(minutes=-timezone_offset)

    data = []
    for log in logs:
        local_ts = log.timestamp + local_offset
        data.append({
            "ID": log.id,
            "Kapal (Vessel)": log.vessel_ship,
            "Lokasi Kerja": log.location_work,
            "O2 (%)": log.o2,
            "CO (ppm)": log.co,
            "Status": log.knn_class.value,
            "Waktu Perekaman": local_ts.strftime("%Y-%m-%d %H:%M:%S")
        })

    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame(columns=["ID", "Kapal (Vessel)", "Lokasi Kerja", "O2 (%)", "CO (ppm)", "Status", "Waktu Perekaman"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Log Kualitas Udara')
        
        # Ambil workbook dan sheet untuk kustomisasi gaya
        workbook = writer.book
        worksheet = writer.sheets['Log Kualitas Udara']
        
        # 1. Desain Font & Warna Header (Sesuai tema Navy Slate-900 dasbor)
        header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='0F172A', end_color='0F172A', fill_type='solid') # Slate-900
        header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        # 2. Garis Batas Sel (Borders)
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'), # slate-300
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )
        
        # Terapkan gaya header
        for col_num in range(1, len(df.columns) + 1):
            cell = worksheet.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border
            
        # 3. Desain Zebra Striping untuk Data Rows (Baris Belang-Belang)
        data_font = Font(name='Arial', size=10)
        zebra_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid') # slate-50
        
        for row_idx in range(2, len(df) + 2):
            is_zebra = (row_idx % 2 == 0)
            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.font = data_font
                cell.border = thin_border
                
                # Gunakan zebra fill pada baris genap
                if is_zebra:
                    cell.fill = zebra_fill
                    
                # Format perataan teks (Alignment)
                col_name = df.columns[col_idx - 1]
                if col_name in ["ID", "KNN Status", "Waktu Perekaman"]:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='left', vertical='center')
                    
        # 4. Atur Tinggi Baris (Row Heights)
        worksheet.row_dimensions[1].height = 28 # Tinggi header lebih longgar
        for r in range(2, len(df) + 2):
            worksheet.row_dimensions[r].height = 20
            
        # 5. Penyesuaian Lebar Kolom Otomatis (Auto-Fit Column Width)
        for col in worksheet.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = str(cell.value or '')
                if len(val) > max_len:
                    max_len = len(val)
            worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)
            
        # Tampilkan garis gridline bawaan Excel
        worksheet.views.sheetView[0].showGridLines = True

    output.seek(0)

    # Nama file dinamis
    filename = "Laporan_Kualitas_Udara"
    if start_dt:
        filename += f"_{start_dt.strftime('%Y%m%d')}"
    if end_dt:
        filename += f"_to_{end_dt.strftime('%Y%m%d')}"
    filename += ".xlsx"

    return output, filename
