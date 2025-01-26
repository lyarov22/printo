# Production Guide for Printo

## Installation Steps

1. **Update and upgrade the system:**:
   ```bash
   sudo apt update && sudo apt upgrade

2. **Install necessary system packages:**:
   ```bash
   sudo apt install cups libcups2-dev

2.1 **Install dev deps**
    ```bash
    sudo apt install cups-pdf

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt

4. **Create the `.env` file**:
   - In the root directory, create a file named `.env`.
   - Add the following content and replace values as necessary:
     ```env
      PROJECT_NAME=MyApp
      API_V1_STR=/api/v1
      DATABASE_URL=postgresql+asyncpg://printo:printo@db:5432/printo
      SECRET_KEY=supersecretkey
      ALGORITHM=HS256
      ACCESS_TOKEN_EXPIRE_MINUTES=10080 #1 week
      PRICE_PER_PAGE=40
      PRINTER_NAME=PDF
     ```

5. **Run the server:**:
   ```bash
   uvicorn main:app --reload
