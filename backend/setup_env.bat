@echo off
echo 1. Creating Python virtual environment in 'venv'...
if not exist venv (
    python -m venv venv
    echo Virtual environment created successfully.
) else (
    echo Virtual environment 'venv' already exists. Skipping creation.
)

echo 2. Activating virtual environment and upgrading pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo 3. Installing dependencies from requirements.txt...
pip install -r requirements.txt

echo 4. Registering Jupyter Kernel for the virtual environment...
python -m ipykernel install --user --name=aiot-klasifikasi-udara --display-name="Python (AIoT-Klasifikasi-Udara)"

echo Environment setup complete!
