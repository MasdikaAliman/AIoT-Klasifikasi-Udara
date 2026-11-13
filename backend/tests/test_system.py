import os
import sys
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src folder to sys path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from database import Base, AirQualityLog, AirQualityStatus
from knn_classifier import predict_air_quality

# Mock Database Setup
from sqlalchemy.pool import StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_predict_classes():
    # Test O2 & CO combinations to ensure classification runs and returns correct labels
    # Normal air quality
    label_safe = predict_air_quality(20.9, 0.0)
    assert label_safe in ["Safe", "Aware", "Danger"]
    
    # Check that predictions for distinct O2 and CO return string outputs
    assert isinstance(label_safe, str)

def test_database_save_and_retrieve(db_session):
    # Test database write
    new_log = AirQualityLog(
        vessel_ship="TEST_VESSEL_SHIP",
        location_work="TEST_ENGINE_ROOM",
        o2=20.5,
        co=8.0,
        knn_class=AirQualityStatus.Safe,
        timestamp=datetime.utcnow()
    )
    db_session.add(new_log)
    db_session.commit()
    
    # Query and verify written record
    saved_log = db_session.query(AirQualityLog).first()
    assert saved_log is not None
    assert saved_log.vessel_ship == "TEST_VESSEL_SHIP"
    assert saved_log.location_work == "TEST_ENGINE_ROOM"
    assert saved_log.o2 == 20.5
    assert saved_log.co == 8.0
    assert saved_log.knn_class == AirQualityStatus.Safe

def test_download_excel(db_session):
    from fastapi.testclient import TestClient
    from main import app, get_db
    import pandas as pd
    import io

    # Override get_db to use testing db_session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db

    # Insert some dummy logs
    db_session.add_all([
        AirQualityLog(
            vessel_ship="SHIP_A",
            location_work="ROOM_1",
            o2=20.9,
            co=1.0,
            knn_class=AirQualityStatus.Safe,
            timestamp=datetime(2026, 8, 2, 10, 0, 0)
        ),
        AirQualityLog(
            vessel_ship="SHIP_B",
            location_work="ROOM_2",
            o2=20.0,
            co=15.0,
            knn_class=AirQualityStatus.Aware,
            timestamp=datetime(2026, 8, 2, 12, 0, 0)
        )
    ])
    db_session.commit()

    client = TestClient(app)

    # Test downloading without filters
    response = client.get("/api/logs/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "Laporan_Kualitas_Udara" in response.headers["content-disposition"]

    # Parse Excel and verify content
    excel_file = io.BytesIO(response.content)
    df = pd.read_excel(excel_file, engine='openpyxl')
    assert len(df) == 2
    assert list(df.columns) == ["ID", "Kapal (Vessel)", "Lokasi Kerja", "O2 (%)", "CO (ppm)", "Status", "Waktu Perekaman"]
    assert df.iloc[0]["Kapal (Vessel)"] == "SHIP_A"
    assert df.iloc[1]["Status"] == "Aware"

    # Test downloading with start_time filter
    response_filtered = client.get("/api/logs/download?start_time=2026-08-02T11:00:00")
    assert response_filtered.status_code == 200
    df_filtered = pd.read_excel(io.BytesIO(response_filtered.content), engine='openpyxl')
    assert len(df_filtered) == 1
    assert df_filtered.iloc[0]["Kapal (Vessel)"] == "SHIP_B"

    # Test downloading with timezone_offset= -420 (GMT+7, WIB)
    response_tz = client.get("/api/logs/download?timezone_offset=-420")
    assert response_tz.status_code == 200
    df_tz = pd.read_excel(io.BytesIO(response_tz.content), engine='openpyxl')
    # UTC 10:00:00 + 7 hours = 17:00:00 WIB
    assert df_tz.iloc[0]["Waktu Perekaman"] == "2026-08-02 17:00:00"
    # UTC 12:00:00 + 7 hours = 19:00:00 WIB
    assert df_tz.iloc[1]["Waktu Perekaman"] == "2026-08-02 19:00:00"

    # Clean overrides
    app.dependency_overrides.clear()

def test_safe_parsing_and_null_payload():
    from main import safe_float, safe_str, on_message
    import json
    from unittest.mock import MagicMock

    # Test safe_float handles None, strings, NaNs, and invalids gracefully
    assert safe_float(None, 20.9) == 20.9
    assert safe_float("null", 20.9) == 20.9
    assert safe_float(float("nan"), 20.9) == 20.9
    assert safe_float("invalid", 5.0) == 5.0
    assert safe_float("18.5", 20.9) == 18.5
    assert safe_float(19.2, 20.9) == 19.2

    # Test safe_str
    assert safe_str(None, "DEFAULT") == "DEFAULT"
    assert safe_str("", "DEFAULT") == "DEFAULT"
    assert safe_str("SHIP_X", "DEFAULT") == "SHIP_X"

    # Test on_message does not throw TypeError on null payload
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.topic = "engine_room/sensor"
    # Null values in JSON like ArduinoJson serialization of NaN
    mock_msg.payload = json.dumps({
        "vessel_ship": None,
        "location_work": None,
        "o2": None,
        "co": None
    }).encode("utf-8")

    # This should execute cleanly without raising TypeError
    on_message(mock_client, None, mock_msg)

