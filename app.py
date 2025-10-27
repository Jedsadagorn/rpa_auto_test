from flask import Flask, request, jsonify
import asyncio
import threading
from datetime import datetime
import uuid
from supabase import create_client, Client

SUPABASE_URL = "https://cnexrwsphsqdykauuaga.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg"

# Import ฟังก์ชันหลักจาก code เดิม
# ในที่นี้จะ import main และ get_extracted_data_requests
# (สมมติว่าเก็บ code เดิมไว้ในไฟล์ชื่อ fda_complete_login.py)
# from fda_complete_login import main, get_extracted_data_requests

app = Flask(__name__)

# เก็บสถานะของ jobs
jobs = {}

class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

def run_automation_async(job_id, reference_number, msg_id):
    """
    ฟังก์ชันสำหรับรัน automation แบบ async
    รองรับการ retry สูงสุด 3 ครั้งหากไม่สำเร็จ
    และอัปเดตสถานะไปที่ database เมื่อ fail
    """
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            jobs[job_id]["status"] = JobStatus.RUNNING
            jobs[job_id]["started_at"] = datetime.now().isoformat()
            jobs[job_id]["retry_count"] = retry_count + 1
            
            # รัน main function แบบ async
            # ต้องสร้าง event loop ใหม่เพราะรันใน thread แยก
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Import main function ที่นี่เพื่อหลีกเลี่ยง circular import
            from fda_complete_login import main
            
            # รัน main function และรับค่า return
            result = loop.run_until_complete(main(reference_number))
            loop.close()
            
            # ตรวจสอบผลลัพธ์
            # สมมติว่า main() return "Complete" เมื่อสำเร็จ
            if result == "Completed":
                jobs[job_id]["status"] = JobStatus.COMPLETED
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                jobs[job_id]["message"] = f"Automation completed successfully (Attempt {retry_count + 1}/{max_retries})"

                # # ยิง API เพื่ออัปเดตสถานะใน database
                # update_queue_supabase(reference_number, job_id, msg_id)
                break  # ออกจาก loop เมื่อสำเร็จ
            else:
                # ถ้าผลลัพธ์ไม่ใช่ Complete
                retry_count += 1
                if retry_count < max_retries:
                    jobs[job_id]["status"] = JobStatus.RUNNING
                    jobs[job_id]["message"] = f"Incomplete result: {result}. Retrying... (Attempt {retry_count + 1}/{max_retries})"
                    # อาจเพิ่ม delay ก่อน retry
                    import time
                    time.sleep(2)  # รอ 2 วินาทีก่อน retry
                else:
                    # ครบจำนวน retry แล้ว
                    error_message = f"Failed after {max_retries} attempts. Last result: {result}"
                    jobs[job_id]["status"] = JobStatus.FAILED
                    jobs[job_id]["completed_at"] = datetime.now().isoformat()
                    jobs[job_id]["error"] = error_message
                    
                    # ยิง API เพื่ออัปเดตสถานะใน database
                    update_database_status(reference_number, job_id)
                    
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                jobs[job_id]["status"] = JobStatus.RUNNING
                jobs[job_id]["message"] = f"Error occurred: {str(e)}. Retrying... (Attempt {retry_count + 1}/{max_retries})"
                # อาจเพิ่ม delay ก่อน retry
                import time
                time.sleep(2)
                if 'loop' in locals():
                    loop.close()
            else:
                # ครบจำนวน retry แล้ว
                error_message = f"Failed after {max_retries} attempts. Last error: {str(e)}"
                jobs[job_id]["status"] = JobStatus.FAILED
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
                if 'loop' in locals():
                    loop.close()
                
                # ยิง API เพื่ออัปเดตสถานะใน database
                update_database_status(reference_number, "Failed", error_message)

def update_queue_supabase(reference_number, job_id, msg_id):

    """
    ฟังก์ชันสำหรับยิง API เพื่ออัปเดตสถานะใน database
    """
    import requests
    # กำหนด URL ของ API
    api_url = "http://localhost:3000/api/rpa_auto"
    # กำหนด headers สำหรับ request
    headers = {
        'Content-Type': 'application/json'
    }

    payload = {
        "msg_id": msg_id,
        "job_id": job_id,
        "reference_number": reference_number
    }

    try:
        request = requests.delete(api_url, headers=headers, json=payload)

        if request.status_code == 200:
            print(f"✅ Successfully fetched records from API")
        else:
            print(f"❌ API request failed with status code: {request.status_code}")
    except Exception as e:
        print(f"Error occurred: {str(e)}")
    

def update_database_status(reference_number, status, message=None):
    """
    ฟังก์ชันสำหรับยิง API เพื่ออัปเดตสถานะใน database
    """
    import requests
    
    # กำหนด URL ของ API
    api_url = "https://cnexrwsphsqdykauuaga.supabase.co/rest/v1/jobs?reference_number=eq." + reference_number
    # กำหนด headers สำหรับ request
    headers = {
        'Content-Type': 'application/json',
        'apiKey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg',
        'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg'
    }
        
    # เตรียม payload
    payload = {
        "status": status,
    }
    
    try:
        # ส่ง PUT request ไปยัง API
        response = requests.patch(api_url, headers=headers, json=payload)
        
        # ตรวจสอบ response
        if response.status_code == 204:
            print(f"✅ Successfully updated database status for {reference_number}")
            return True
        else:
            print(f"⚠️ Failed to update database. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout while updating database for {reference_number}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Error updating database: {str(e)}")
        return False

@app.route('/api/automation/start', methods=['POST'])
def start_automation():
    """
    เริ่มต้น automation process
    
    Request Body:
    {
        "job_id": "uuid",
        "reference_number": "AROP500001263"
        "msg_id": 1
    }
    
    Response:
    {
        "job_id": "uuid",
        "reference_number": "AROP500001263",
        "status": "pending",
        "message": "Automation job created"
    }
    """
    try:
        # รับข้อมูลจาก request
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": "No JSON data provided"
            }), 400
        
        reference_number = data.get('reference_number')
        job_id = data.get('job_id')
        msg_id = data.get('msg_id')
        
        if not reference_number:
            return jsonify({
                "error": "reference_number is required"
            }), 400
        
        # สร้าง job entry
        jobs[job_id] = {
            "job_id": job_id,
            "reference_number": reference_number,
            "status": JobStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "message": None
        }
        
        # เริ่ม automation ใน thread แยก
        thread = threading.Thread(
            target=run_automation_async,
            args=(job_id, reference_number, msg_id),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "reference_number": reference_number,
            "status": JobStatus.PENDING,
            "message": "Automation job created successfully"
        }), 202
        
    except Exception as e:
        return jsonify({
            "error": f"Failed to start automation: {str(e)}"
        }), 500

@app.route('/api/automation/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """
    ตรวจสอบสถานะของ job
    
    Response:
    {
        "job_id": "uuid",
        "reference_number": "AROP500001263",
        "status": "running",
        "created_at": "2025-01-15T10:00:00",
        "started_at": "2025-01-15T10:00:05",
        "completed_at": null,
        "error": null,
        "message": null
    }
    """
    if job_id not in jobs:
        return jsonify({
            "error": "Job not found"
        }), 404
    
    return jsonify(jobs[job_id]), 200

@app.route('/api/automation/jobs', methods=['GET'])
def list_jobs():
    """
    แสดงรายการ jobs ทั้งหมด
    
    Query Parameters:
    - status: filter by status (optional)
    - limit: number of jobs to return (default: 50)
    
    Response:
    {
        "total": 10,
        "jobs": [...]
    }
    """
    status_filter = request.args.get('status')
    limit = int(request.args.get('limit', 50))
    
    # กรอง jobs ตาม status
    filtered_jobs = jobs.values()
    if status_filter:
        filtered_jobs = [j for j in filtered_jobs if j['status'] == status_filter]
    
    # เรียงตามเวลาที่สร้างล่าสุด
    sorted_jobs = sorted(
        filtered_jobs,
        key=lambda x: x['created_at'],
        reverse=True
    )[:limit]
    
    return jsonify({
        "total": len(sorted_jobs),
        "jobs": sorted_jobs
    }), 200

@app.route('/api/automation/validate', methods=['POST'])
def validate_reference():
    """
    ตรวจสอบว่า reference_number มีข้อมูลใน database หรือไม่
    
    Request Body:
    {
        "reference_number": "AROP500001263"
    }
    
    Response:
    {
        "valid": true,
        "reference_number": "AROP500001263",
        "data_count": 5,
        "message": "Reference number is valid"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": "No JSON data provided"
            }), 400
        
        reference_number = data.get('reference_number')
        
        if not reference_number:
            return jsonify({
                "error": "reference_number is required"
            }), 400
        
        # Import function
        from fda_complete_login import get_extracted_data_requests
        
        # ดึงข้อมูลจาก API
        extracted_data = get_extracted_data_requests(reference_number)
        
        if extracted_data and len(extracted_data) > 0:
            return jsonify({
                "valid": True,
                "reference_number": reference_number,
                "data_count": len(extracted_data),
                "message": "Reference number is valid"
            }), 200
        else:
            return jsonify({
                "valid": False,
                "reference_number": reference_number,
                "data_count": 0,
                "message": "No data found for this reference number"
            }), 404
            
    except Exception as e:
        return jsonify({
            "error": f"Validation failed: {str(e)}"
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal server error"
    }), 500

if __name__ == '__main__':
    print("🚀 Starting FDA Automation API Server...")
    print("📍 Server running on http://localhost:5003")
    print("\n📚 Available endpoints:")
    print("  POST /api/automation/start")
    print("  GET  /api/automation/status/<job_id>")
    print("  GET  /api/automation/jobs")
    print("  POST /api/automation/validate")
    print("\n")
    
    app.run(
        host='0.0.0.0',
        port=5003,
        debug=True
    )