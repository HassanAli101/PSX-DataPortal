import os
import boto3
import pdfplumber
from botocore.exceptions import ClientError
import psycopg2
from psycopg2 import sql
from datetime import datetime
from base64 import b64decode

# AWS S3 Client
s3 = boto3.client('s3')

# Database connection setup
def get_db_connection():
    return psycopg2.connect(os.environ['NEONDB'])

# Helper function: Parse file date
def parse_file_date(file_name):
    try:
        prefix, raw_date = file_name.split("_")
        year = raw_date[:4]
        day = raw_date[4:6]
        month_str = raw_date[6:9].lower()
        month = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12"
        }.get(month_str, "00")

        if month == "00":
            raise ValueError("Invalid month in file name.")

        return f"{day}-{month}-{year[2:]}"
    except Exception as e:
        raise ValueError(f"Error parsing date from file name: {file_name}. Error: {e}")

# Helper function: Parse PDF table
def parse_pdf_table(pdf_path):
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_data = page.extract_words()
            page_data.sort(key=lambda x: (x['top'], x['x0']))

            current_row = []
            current_top = page_data[0]['top'] if page_data else None

            for item in page_data:
                if abs(item['top'] - current_top) > 5:
                    rows.append(current_row)
                    current_row = []
                    current_top = item['top']
                current_row.append(item['text'])

            if current_row:
                rows.append(current_row)

    data = []
    detected_technology = False
    for row in rows:
        if detected_technology and len(row) > 3:
            data.append([
                ' '.join(row[1:-7]),  # company_name
                *map(float, row[-7:])  # turnover, prev_rate, etc.
            ])
        if row == ['***FERTILIZER***']:
            detected_technology = False
        if row == ['***TECHNOLOGY', '&', 'COMMUNICATION***']:
            detected_technology = True

    return data

# Lambda handler
def lambda_handler(event, context):
    try:
        print(f"Event received: {event}")
        
        # Step 1: Parse input
        file_name = event['file_name']
        bucket_name = os.environ['S3_BUCKET']
        file_content = b64decode(event['file_content'])

        # Step 2: Parse file date
        try:
            date = parse_file_date(file_name)
            print(f"Parsed date: {date}")
        except ValueError as e:
            print(f"Date parsing error: {e}")
            return {"statusCode": 400, "body": str(e)}

        # Step 3: Save file locally
        temp_file_path = f"/tmp/{file_name}"
        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(file_content)
        print(f"File saved locally: {temp_file_path}")

        # Step 4: Parse PDF
        try:
            rows = parse_pdf_table(temp_file_path)
            print(f"Parsed rows: {rows}")
        except Exception as e:
            print(f"PDF parsing error: {e}")
            raise

        # Step 5: Insert data into NeonDB
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            for row in rows:
                print(f"Inserting row: {row}")
                # Execute SQL insert
            conn.commit()
        except Exception as e:
            print(f"Database error: {e}")
            raise

        # Step 6: Upload to S3
        try:
            s3.upload_file(temp_file_path, bucket_name, file_name)
            print(f"File uploaded to S3: {bucket_name}/{file_name}")
        except Exception as e:
            print(f"S3 upload error: {e}")
            raise

        return {"statusCode": 200, "body": "Data processed and stored successfully."}
    
    except Exception as e:
        print(f"Unhandled error: {e}")
        return {"statusCode": 500, "body": f"Error: {e}"}

