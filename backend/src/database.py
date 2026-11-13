import os
import enum
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load configuration from environment file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./air_quality.db")

# If SQLite is used, allow multi-threading access
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AirQualityStatus(str, enum.Enum):
    Safe = "Safe"
    Aware = "Aware"
    Danger = "Danger"

class AirQualityLog(Base):
    __tablename__ = "air_quality_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    vessel_ship = Column(String, index=True)
    location_work = Column(String)
    o2 = Column(Float)
    co = Column(Float)
    knn_class = Column(Enum(AirQualityStatus), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
