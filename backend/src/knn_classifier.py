import os
import joblib
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# Load paths from env
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
model_rel = os.getenv("MODEL_PATH", "backend/utils/knn_model.joblib")
scaler_rel = os.getenv("SCALER_PATH", "backend/utils/scaler.joblib")

MODEL_PATH = os.path.join(root_dir, model_rel)
SCALER_PATH = os.path.join(root_dir, scaler_rel)

def predict_air_quality(o2: float, co: float) -> str:
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        raise FileNotFoundError(
            f"Model or Scaler not found.\nExpected model: {MODEL_PATH}\nExpected scaler: {SCALER_PATH}\n"
            f"Please run the Jupyter Notebook at backend/utils/KNN_ANALYSIS.ipynb to train and save the model artifacts."
        )
    
    knn = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    
    features = np.array([[o2, co]])
    scaled_features = scaler.transform(features)
    prediction = knn.predict(scaled_features)[0]
    return str(prediction)
