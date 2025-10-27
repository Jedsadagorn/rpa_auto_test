import requests
import asyncio
import nodriver as uc
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import os
from supabase import create_client, Client
import base64
from nodriver import cdp


SUPABASE_URL = "https://cnexrwsphsqdykauuaga.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg"
BUCKET_NAME = "screenshots"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class GlobalState:
    company_name = ""

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def take_screenshot(page, step_name: str, reference_number: str):
    """ถ่าย screenshot แล้วอัปโหลดเข้า Supabase"""
    os.makedirs("screenshots", exist_ok=True)
    file_name = f"{step_name}.png"
    local_path = os.path.join("screenshots", file_name)

    # บันทึกภาพ
    await page.save_screenshot(local_path, full_page=True)
    print(f"📸 Screenshot saved: {local_path}")

    # อัปโหลดเข้า Supabase -> {reference_number}/screenshots/{file_name}
    storage_path = f"{reference_number}/screenshots/{file_name}"
    with open(local_path, "rb") as f:
        print(f"☁️ Uploading to Supabase: {storage_path}")
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path, f, {"upsert": "true"}
        )
    print(f"☁️ Uploaded to Supabase: {storage_path}")
    return storage_path

def download_and_upload_file(file_url: str, reference_number: str, fileName: str):
    """ดาวน์โหลดไฟล์จาก URL แล้วอัปโหลดเข้า Supabase"""
    os.makedirs("downloads", exist_ok=True)
    file_name = reference_number + "_" + fileName or "downloaded_file"
    local_path = os.path.join("downloads", file_name)

    print(f"⬇️ Downloading file: {file_url}")
    resp = requests.get(file_url)
    if resp.status_code != 200:
        raise Exception(f"❌ Failed to download ({resp.status_code}): {file_url}")

    with open(local_path, "wb") as f:
        f.write(resp.content)

    # อัปโหลดเข้า Supabase -> {reference_number}/downloads/{file_name}
    storage_path = f"{reference_number}/downloads/{file_name}.pdf"
    print(f"☁️ Uploading to Supabase: {storage_path}")
    # with open(local_path, "rb") as f:
    #     supabase.storage.from_(BUCKET_NAME).upload(
    #         storage_path, f, {"upsert": "true"}
    #     )
    with open(local_path, "rb") as f:
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path, 
            f, 
            {
                "content-type": "application/pdf",  # ⭐ สำคัญมาก!
                "upsert": "true"
            }
        )
    print(f"☁️ Uploaded to Supabase: {storage_path}")
    return storage_path

async def print_page_and_upload(page, reference_number: str, fileName: str):
    """Print หน้าเว็บเป็น PDF แล้วอัปโหลดเข้า Supabase"""
    os.makedirs("downloads", exist_ok=True)
    file_name = reference_number + "_" + fileName
    local_path = os.path.join("downloads", f"{file_name}.pdf")

    print(f"🖨️ Printing page to PDF: {file_name}")
    
    try:
        # ใช้ CDP command ที่ถูกต้อง
        result = await page.send(
            cdp.page.print_to_pdf(
                print_background=True,
                paper_width=8.27,
                paper_height=11.69,
                margin_top=0.4,
                margin_bottom=0.4,
                margin_left=0.4,
                margin_right=0.4,
                landscape=False
            )
        )
        
        # ดึง PDF data ออกมา (อาจจะเป็น result[0] หรือ result.data)
        if isinstance(result, tuple):
            pdf_base64 = result[0]  # ลองดึงตัวแรก
        else:
            pdf_base64 = result
            
        # Decode PDF data
        # pdf_data = base64.b64decode(result)
        pdf_data = base64.b64decode(pdf_base64)
        
        # เขียนไฟล์
        with open(local_path, "wb") as f:
            f.write(pdf_data)
        
        print(f"✅ PDF created: {local_path}")

        # อัปโหลดเข้า Supabase
        storage_path = f"{reference_number}/downloads/{file_name}.pdf"
        print(f"☁️ Uploading to Supabase: {storage_path}")
        
        with open(local_path, "rb") as f:
            supabase.storage.from_(BUCKET_NAME).upload(
                storage_path, f, {"upsert": "true"}
            )
        
        print(f"✅ Uploaded to Supabase: {storage_path}")
        
        # ลบไฟล์ชั่วคราว
        os.remove(local_path)
        
        return storage_path
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

async def fill_input_with_retry(page, selector: str, value: str, max_retries: int = 3, 
                                wait_time: float = 2, label: str = "input field") -> bool:
    """
    กรอกข้อความใน input field พร้อม retry
    
    Args:
        page: page object
        selector: CSS selector ของ input
        value: ค่าที่ต้องการกรอก
        max_retries: จำนวนครั้งสูงสุดที่จะลอง
        wait_time: เวลารอระหว่าง retry (วินาที)
        label: ชื่อของ input สำหรับแสดงใน log
    
    Returns:
        bool: True ถ้าสำเร็จ, False ถ้าล้มเหลว
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"🔘 Find {label} (ครั้งที่ {retry_count + 1}/{max_retries})")
            input_field = await asyncio.wait_for(page.find(selector, timeout=10), timeout=1000)
            
            if input_field:
                print(f"✅ Found {label}, clearing and entering value")
                await input_field.clear_input()
                await asyncio.sleep(1.5)
                await input_field.send_keys(value)
                print(f"✅ {label} entered: {value}")
                await asyncio.sleep(1)
                return True
            else:
                print(f"ℹ️ {label} not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                    await asyncio.sleep(wait_time)
                
        except Exception as e:
            print(f"⚠️ Error entering {label} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถกรอก {label} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False

async def select_dropdown_with_retry(page, selector, value, max_retries=3, wait_time=2, label="dropdown"):
    """
    เลือกค่าใน dropdown พร้อม retry
    
    Args:
        page: page object
        selector: CSS selector ของ dropdown
        value: ค่าที่ต้องการเลือก
        max_retries: จำนวนครั้งสูงสุดที่จะลอง (default: 3)
        wait_time: เวลารอระหว่าง retry (วินาที)
        label: ชื่อของ dropdown สำหรับแสดงใน log
    
    Returns:
        bool: True ถ้าเลือกสำเร็จ, False ถ้าล้มเหลว
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"🔘 Find {label} (ครั้งที่ {retry_count + 1}/{max_retries})")
            dropdown = await asyncio.wait_for(page.find(selector, timeout=10), timeout=1000)
            
            if dropdown:
                print(f"✅ Found {label}, selecting value: {value}")
                
                await dropdown.apply(f'''
                    function(element) {{
                        element.value = "{value}";
                        element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                ''')
                
                print(f"✅ Selected {label}: {value}")
                await asyncio.sleep(1)
                return True  # สำเร็จ
            else:
                print(f"ℹ️ {label} not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                    await asyncio.sleep(wait_time)
                
        except Exception as e:
            print(f"⚠️ Error selecting {label} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถเลือก {label} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False  # ล้มเหลว

async def click_selector_with_retry(page, selector, max_retries=3, wait_time=2, 
                                     button='left', click_count=1):
    """คลิกปุ่มจาก CSS selector พร้อม retry และ mouse_click"""
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"🔘 Find Click selector: {selector} (ครั้งที่ {retry_count + 1}/{max_retries})")
            link = await asyncio.wait_for(page.find(selector, timeout=10), timeout=1000)
            
            if link:
                print(f"✅ Click to {selector}")
                await link.mouse_click(button, click_count)
                print(f"✅ Clicked {selector}")
                await asyncio.sleep(0.5)
                return True
            else:
                print(f"ℹ️ {selector} not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(wait_time)
                
        except Exception as e:
            print(f"⚠️ Error clicking {selector} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถคลิก {selector} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False

async def click_input_with_retry(page, selector, field_name="Button", max_retries=3, wait_time=2, click_count=1):
    """
    พยายามค้นหาและคลิก input button พร้อม retry
    
    Args:
        page: page object
        selector: CSS selector ของ input button
        field_name: ชื่อของ button สำหรับ logging (default: "Button")
        max_retries: จำนวนครั้งสูงสุดที่จะลอง (default: 3)
        wait_time: เวลารอระหว่าง retry (วินาที)
        click_count: จำนวนครั้งที่จะคลิก (default: 1)
    
    Returns:
        bool: True ถ้าคลิกสำเร็จ, False ถ้าล้มเหลว
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"🔘 Find and click {field_name} (ครั้งที่ {retry_count + 1}/{max_retries})")
            button = await asyncio.wait_for(
                page.find(selector, timeout=5), 
                timeout=10
            )
            
            if button:
                await button.mouse_click(str, click_count)
                print(f"✅ Clicked {field_name} ({click_count} time(s))")
                await asyncio.sleep(0.5)
                return True  # สำเร็จ
            else:
                print(f"ℹ️ {field_name} button not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                    await asyncio.sleep(wait_time)
                    
        except Exception as e:
            print(f"⚠️ Error clicking {field_name} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถคลิก {field_name} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False  # ล้มเหลว


async def click_with_retry(page, button_text, max_retries=3, wait_time=2):
    """
    พยายามค้นหาและคลิกปุ่มพร้อม retry
    
    Args:
        page: page object
        button_text: ข้อความบนปุ่มที่ต้องการคลิก
        max_retries: จำนวนครั้งสูงสุดที่จะลอง (default: 3)
        wait_time: เวลารอระหว่าง retry (วินาที)
    
    Returns:
        bool: True ถ้าคลิกสำเร็จ, False ถ้าล้มเหลว
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"🔘 Find Click {button_text} (ครั้งที่ {retry_count + 1}/{max_retries})")
            link = await asyncio.wait_for(page.find(button_text, timeout=10), timeout=1000)
            
            if link:
                print(f"✅ Click to {button_text}")
                await link.click()
                print(f"✅ Navigated to {button_text}")
                await asyncio.sleep(1)
                return True  # สำเร็จ
            else:
                print(f"ℹ️ {button_text} button not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                    await asyncio.sleep(wait_time)
                
        except Exception as e:
            print(f"⚠️ Error clicking {button_text} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถคลิกปุ่ม {button_text} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False

async def input_with_retry(page, selector, value, field_name="Field", max_retries=3, wait_time=2):
    """
    พยายามค้นหาและกรอกข้อมูลพร้อม retry
    
    Args:
        page: page object
        selector: CSS selector ของ input field
        value: ค่าที่ต้องการกรอก
        field_name: ชื่อของ field สำหรับ logging (default: "Field")
        max_retries: จำนวนครั้งสูงสุดที่จะลอง (default: 3)
        wait_time: เวลารอระหว่าง retry (วินาที)
    
    Returns:
        bool: True ถ้ากรอกสำเร็จ, False ถ้าล้มเหลว
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"📝 Find and input {field_name} (ครั้งที่ {retry_count + 1}/{max_retries})")
            input_field = await asyncio.wait_for(
                page.find(selector, timeout=5), 
                timeout=10
            )
            
            if input_field:
                await asyncio.sleep(0.5)
                await input_field.send_keys(value)
                print(f"✅ {field_name} entered: {value}")
                await asyncio.sleep(1)
                return True  # สำเร็จ
            else:
                print(f"ℹ️ {field_name} field not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                    await asyncio.sleep(wait_time)
                    
        except Exception as e:
            print(f"⚠️ Error entering {field_name} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถกรอก {field_name} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False  # ล้มเหลว


async def text_with_retry(page, text, max_retries=3, wait_time=2):
    """
    พยายามค้นหาและกรอกข้อมูลพร้อม retry
    
    Args:
        page: page object
        text: ข้อความที่ต้องการค้นหา
        max_retries: จำนวนครั้งสูงสุดที่จะลอง (default: 3)
        wait_time: เวลารอระหว่าง retry (วินาที)
    
    Returns:
        bool: True ถ้ากรอกสำเร็จ, False ถ้าล้มเหลว
    """
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"📝 Find {text} (ครั้งที่ {retry_count + 1}/{max_retries})")
            text_field = await asyncio.wait_for(
                    page.find(text, timeout=10),
                    timeout=1000
                )
            
            if text_field:
                print(f"✅ Found {text}")
                await asyncio.sleep(1)
                return True  # สำเร็จ
            else:
                print(f"ℹ️ {text} not found (ครั้งที่ {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                    await asyncio.sleep(wait_time)
                    
        except Exception as e:
            print(f"⚠️ Error finding {text} (ครั้งที่ {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"🔄 รอ {wait_time} วินาที แล้วลองใหม่...")
                await asyncio.sleep(wait_time)
    
    print(f"❌ ไม่สามารถค้นหา {text} ได้หลังจากลองครบ {max_retries} ครั้ง")
    return False  # ล้มเหลว

def update_step_job(reference_number, payload):
    try:
        # กำหนด URL ของ API
        api_url = "https://cnexrwsphsqdykauuaga.supabase.co/rest/v1/jobs?reference_number=eq." + reference_number
        # กำหนด headers สำหรับ request
        headers = {
            'Content-Type': 'application/json',
            'apiKey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg',
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg'
        }
        
        # ส่ง PUT request ไปยัง API
        responseupdate = requests.patch(api_url, headers=headers, json=payload)

        # ตรวจสอบ status code
        if responseupdate.status_code == 204:
            print(f"✅ Successfully fetched records from API")
        else:
            print(f"❌ API request failed with status code: {responseupdate.status_code}")
            print(f"Responseupdate: {responseupdate.text}")

    except Exception as e:
        print("❌ Error fetching data from API:", e)

async def action_sky_net(page, detail, license_list, input_data, invoice_number, stepJob, mapping_type): 
    """ฟังก์ชันหลักในการทำงานกับ FDA website"""
    
    mapping_type_name = next(
        (item["value"] for item in mapping_type if item["label"] == detail["permit_type"]),
        None
    )
    mapping_type_value = mapping_type_name
                
    print("🔘 Selecting Type")
    success_type = await select_dropdown_with_retry(
        page,
        selector='select[name*="ctl00$ContentPlaceHolder1$DropDownList1"], select[id*="ctl00_ContentPlaceHolder1_DropDownList1"]',
        value=mapping_type_value,
        label="Type dropdown",
        max_retries=3,
        wait_time=2
    )

    if not success_type:
        print("⚠️ ไม่สามารถเลือก Type ได้")
     
    # Find and enter invoice number
    print("📝 Entering invoice")
    success_invoice_input = await fill_input_with_retry(
        page,
        selector='input[name*="ctl00$ContentPlaceHolder1$TextBox1"], input[id="ctl00_ContentPlaceHolder1_TextBox1"]',
        value=detail["permit_id"],
        label="Invoice input",
        max_retries=3,
        wait_time=2
    )

    if not success_invoice_input:
        print("⚠️ ไม่สามารถกรอก Invoice ได้")

    search_invoice_click = await click_selector_with_retry(
        page, 
        'input[name*="ctl00$ContentPlaceHolder1$Button1"], input[id="ctl00_ContentPlaceHolder1_Button1"]',
        button='left',
        click_count=2
    )

    if not search_invoice_click:
        print("❌ ไม่สามารถคลิก Search Invoice ได้")

    # ======= Search through table with pagination =======
    found = False
    current_page = 1
    max_pages = 100
    target_data_found = False
    
    print("📋 Starting search through all pages for table data...")
    
    while not found and current_page <= max_pages:
        print(f"\n📄 Searching on page {current_page}...")
        
        try:
            # Wait for table to load
            print(f"⏳ Waiting for table to load...")
            
            try:
                await page.select('table#ctl00_ContentPlaceHolder1_RadGrid1_ctl00', timeout=300)
                print(f"✅ Table element found")
            except Exception as e:
                print(f"❌ Table not loaded after 30 seconds: {e}")
                
                # Check for Next button
                next_button = await page.select('input[title*="Next"], a[title*="Next"]', timeout=2)
                if next_button:
                    print(f"🔄 Clicking next page button...")
                    await next_button.click()
                    await page.sleep(3)
                    current_page += 1
                    continue
                else:
                    print("ℹ️ No next page available, stopping search")
                    break
            
            await page.sleep(1)
            
            # Get number of rows in table
            total_rows_json = await page.evaluate('''
                (() => {
                    const table = document.querySelector('table#ctl00_ContentPlaceHolder1_RadGrid1_ctl00');
                    if (!table) return JSON.stringify(0);
                    const rows = table.querySelectorAll('tbody tr');
                    return JSON.stringify(rows.length);
                })()
            ''')
            
            total_rows = json.loads(total_rows_json)
            print(f"✅ Found table with {total_rows} rows on page {current_page}")
            
            if total_rows > 0:
                print("📊 Extracting column 4 and 9 data:")
                target_data_found = False

                # Extract data row by row

                for row_index in range(total_rows):
                    row_data_json = await page.evaluate(f'''
                        (() => {{
                            const table = document.querySelector('table#ctl00_ContentPlaceHolder1_RadGrid1_ctl00');
                            if (!table) return JSON.stringify(null);
                            
                            // หา column index
                            const headers = table.querySelectorAll('thead th');
                            let newLicenseColumnIndex = -1;
                            let productCodeColumnIndex = -1;
                            let productRemarkColumnIndex = -1;
                            let remarkColumnIndex = -1;
                            
                            headers.forEach((header, index) => {{
                                const headerText = header.textContent.trim();
                                if (headerText.includes('รหัสใหม่')) {{
                                    newLicenseColumnIndex = index;
                                }}
                                if (headerText.includes('CAT_NO')) {{
                                    productCodeColumnIndex = index;
                                }}else if(headerText.includes('เลขใบสำคัญ')) {{
                                    productCodeColumnIndex = index;
                                }}
                                if (headerText.includes('รายละเอียด')) {{
                                    productRemarkColumnIndex = index;
                                }}
                                if (headerText.includes('หมายเหตุ')) {{
                                    remarkColumnIndex = index;
                                }}
                            }});
                            
                            // ถ้าไม่เจอ column "รหัสใหม่" ให้ return null
                            if (newLicenseColumnIndex === -1) return JSON.stringify(null);
                            
                            const row = table.querySelectorAll('tbody tr')[{row_index}];
                            if (!row) return JSON.stringify(null);
                            
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 1) {{
                                return JSON.stringify({{
                                    product_item: cells[productCodeColumnIndex]?.textContent?.trim() || '',
                                    newLicense_number: cells[newLicenseColumnIndex]?.textContent?.trim() || '',
                                    remark_product: productRemarkColumnIndex !== -1 ? cells[productRemarkColumnIndex]?.textContent?.trim() || 'N/A' : 'N/A',
                                    remark: remarkColumnIndex !== -1 ? cells[remarkColumnIndex]?.textContent?.trim() || 'N/A' : 'N/A',
                                    newLicenseColumnIndex: newLicenseColumnIndex,
                                    productCodeColumnIndex: productCodeColumnIndex,
                                    productRemarkColumnIndex: productRemarkColumnIndex,
                                    remarkColumnIndex: remarkColumnIndex,
                                }});
                            }}
                            return JSON.stringify(null);
                        }})()
                    ''')
                    
                    print(row_data_json)
                    row_data = json.loads(row_data_json) if row_data_json else None
                    
                    if row_data:
                        print(f"  Page {current_page} - Row {row_index}: Column {row_data['productCodeColumnIndex']} = '{row_data['product_item']}', Column {row_data['newLicenseColumnIndex']} = '{row_data['newLicense_number']}'")
                        
                        # Check if column 4 matches target
                        if row_data['product_item'] == detail["product_code"]:
                            code = detail["product_code"]
                            target_data_found = True
                            license_number = row_data['newLicense_number']
                            remark_product = row_data['remark_product']
                            remark = row_data['remark']
                            license_list.append({
                                "permit_id": detail["permit_id"],
                                "product_code": code,
                                "license_number": license_number,
                                "remark_product": remark_product,
                                "remark": remark
                            })

                            print(f"  ✅ Found target value {code} at row {row_index}!")
                        elif row_data['product_item'] == detail["permit_id"]:
                            code = detail["product_code"]
                            target_data_found = True
                            license_number = row_data['newLicense_number']
                            remark_product = row_data['remark_product']
                            remark = row_data['remark']
                            license_list.append({
                                "permit_id": detail["permit_id"],
                                "product_code": code,
                                "license_number": license_number,
                                "remark_product": remark_product,
                                "remark": remark
                            })

                
                
                # Process data if target found
                if target_data_found:
                    print(f"\n✅ Target data found on page {current_page}!")
                    found = True
                    break
            
            # Go to next page if not found
            if not target_data_found:
                print(f"ℹ️ No target data found on page {current_page}, checking for next page...")
                
                next_button = None
                try:
                    next_button = await page.select('input[title*="Next"]', timeout=2)
                except:
                    pass
                
                if not next_button:
                    try:
                        next_button = await page.select('a[title*="Next"]', timeout=2)
                    except:
                        pass
                
                if not next_button:
                    try:
                        next_button = await page.select('.rgNumPart input[title="Next Pages"]', timeout=2)
                    except:
                        pass
                
                if next_button:
                    print(f"🔄 Clicking next page button...")
                    await next_button.click()
                    print(f"✅ Clicked next page button")
                    await page.sleep(3)
                    current_page += 1
                else:
                    print("ℹ️ No more pages available, stopping search")
                    break
            
        except Exception as e:
            print(f"❌ Error on page {current_page}: {e}")
            import traceback
            traceback.print_exc()
            break

    # Summary
    if not found:
        if current_page > max_pages:
            print(f"⚠️ Reached maximum pages ({max_pages}), stopping search")
        else:
            print("ℹ️ Search completed - no target data found in any page")
    else:
        print(f"🎉 Successfully found and processed data on page {current_page}")
    
    print(f"\n✅ Completed processing for this detail")

    await asyncio.sleep(1)

def update_input_data(input_data, invoice_number, product_code, step, license_number, status, product_items, items_count, stepJob, reference_number, remark, remark_product):
    """
    อัพเดท input_data ของ item ที่ตรงกับ invoice_number และ item_code
    """

    for invoice in input_data:
        if invoice['invoice_number'] == invoice_number:
            if step == 9:
                invoice['user_data_status'] = "success"
            for item in invoice['invoice_items']:
                if item['item_code'] == product_code:
                    if step == 1: 
                        item['remark_product'] = remark_product
                        item['remark'] = remark

                    elif step == 2: 
                        item['license_number'] = license_number

                    elif step == 3:
                        if product_items != "": 
                            item['product_items'].append(product_items)

                    # ✅ อัปเดตสถานะของ item
                    if items_count == len(item['product_items']) and item["license_number"] != "" and item["remark_product"] != "" and item["remark"] != "":
                        item['status'] = "success"
                    else:
                        item['status'] = status

            # ✅ หลัง loop ทุก item เสร็จแล้ว — เช็คว่าทุกอัน success หรือยัง
            all_success = all(i.get("status") == "success" for i in invoice["invoice_items"])
            if all_success:
                invoice["status"] = "success"

            # ✅ อัปเดตข้อมูลหลังจากแก้ครบทุก item แล้ว
            stepJob["step2"] = input_data
            payload = {"step": stepJob}
            update_step_job(reference_number, payload)

            return True

    return False


async def fill_input_in_iframe(page, input_id: str, value: str, iframe_selector: str = '#detail3TabsFrm') -> bool:
    """
    ฟังก์ชันสำหรับกรอกค่าใน input field ที่อยู่ใน iframe
    
    Args:
        page: Playwright page object
        input_id: ID ของ input field (เช่น 'Product-manufacturingDate')
        value: ค่าที่ต้องการกรอก
        iframe_selector: CSS selector ของ iframe (default: '#detail3TabsFrm')
    
    Returns:
        bool: True ถ้ากรอกสำเร็จ, False ถ้าไม่สำเร็จ
    """
    print(f"📝 Entering {input_id}: {value}")
    
    try:
        # ⭐ Debug: ดู properties ของ input ก่อน
        input_info = await page.evaluate(f'''
            (() => {{
                const iframe = document.querySelector('{iframe_selector}');
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                const input = iframeDoc.querySelector('#{input_id}');
                if (input) {{
                    return {{
                        id: input.id,
                        value: input.value,
                        disabled: input.disabled,
                        readonly: input.readOnly,
                        type: input.type,
                        visible: input.offsetParent !== null,
                        classList: Array.from(input.classList)
                    }};
                }}
                return null;
            }})()
        ''')
        
        if not input_info:
            print(f"❌ Input '{input_id}' not found")
            return False
        
        # ⭐ กรอกค่าแบบละเอียด พร้อม focus และ click
        result = await page.evaluate(f'''
            (() => {{
                const iframe = document.querySelector('{iframe_selector}');
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                const input = iframeDoc.querySelector('#{input_id}');
                
                if (!input) {{
                    return {{ success: false, message: 'Input not found' }};
                }}
                
                // ⭐ ลบ readonly และ disabled ถ้ามี
                input.removeAttribute('readonly');
                input.removeAttribute('disabled');
                input.disabled = false;
                input.readOnly = false;
                
                // ⭐ Click และ Focus
                input.click();
                input.focus();
                
                // ⭐ เคลียร์ค่าเก่า
                input.value = '';
                
                // รอ 100ms
                setTimeout(() => {{
                    // ⭐ กรอกค่าใหม่
                    input.value = '{value}';
                    
                    // ⭐ Trigger หลาย events
                    input.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                    input.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true }}));
                    input.dispatchEvent(new KeyboardEvent('keypress', {{ bubbles: true }}));
                    input.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}, 100);
                
                return {{ 
                    success: true, 
                    value: input.value,
                    message: 'Value setting...'
                }};
            }})()
        ''')
        
        print(f"🔍 Set result: {result}")
        await asyncio.sleep(0.5)
        
        # ⭐ ตรวจสอบว่ากรอกได้จริงหรือไม่
        final_value = await page.evaluate(f'''
            (() => {{
                const iframe = document.querySelector('{iframe_selector}');
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                const input = iframeDoc.querySelector('#{input_id}');
                return input ? input.value : null;
            }})()
        ''')
        
        print(f"🔍 Final value in input: '{final_value}'")
        
        if final_value == value:
            print(f"✅ {input_id} entered successfully!")
            return True
        else:
            print(f"⚠️ Value mismatch! Expected: '{value}', Got: '{final_value}'")
            return False
            
    except Exception as e:
        print(f"❌ Error entering {input_id}: {e}")
        return False

def get_extracted_data_requests(reference_number: str):
    """
    ฟังก์ชันสำหรับดึงข้อมูลจาก API
    
    Args:
        reference_number: เลขอ้างอิง (เช่น 'AROP500001263')
    
    Returns:
        list: รายการข้อมูลที่ดึงมาจาก API
    """
    try:
        # กำหนด URL ของ API
        api_url = "https://cnexrwsphsqdykauuaga.supabase.co/rest/v1/extracted_data?reference_number=eq." + reference_number + "&order=updated_at.desc,id.desc"
        # กำหนด headers สำหรับ request
        headers = {
            'Content-Type': 'application/json',
            'apiKey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg',
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg'
        }
        
        # ส่ง GET request ไปยัง API
        response = requests.get(api_url, headers=headers, timeout=30)
        
        # ตรวจสอบ status code
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Successfully fetched {len(data)} records from API")
            return data
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return []
            
    except requests.exceptions.Timeout:
        print("❌ API request timeout")
        return []
    except requests.exceptions.ConnectionError:
        print("❌ Failed to connect to API")
        return []
    except Exception as e:
        print(f"❌ Error fetching data from API: {e}")
        return []

def get_jobs_data_requests(reference_number: str):
    """
    ฟังก์ชันสำหรับดึงข้อมูลจาก API
    
    Args:
        reference_number: เลขอ้างอิง (เช่น 'AROP50000126')
    
    Returns:
        list: รายการข้อมูลที่ดึงมาจาก API
    """
    try:
        # กำหนด URL ของ API
        api_url = "https://cnexrwsphsqdykauuaga.supabase.co/rest/v1/jobs?reference_number=eq." + reference_number
        # กำหนด headers สำหรับ request
        headers = {
            'Content-Type': 'application/json',
            'apiKey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg',
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg'
        }
        
        # ส่ง GET request ไปยัง API
        response = requests.get(api_url, headers=headers, timeout=30)
        
        # ตรวจสอบ status code
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Successfully fetched {len(data)} records from API")
            return data
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return []
            
    except requests.exceptions.Timeout:
        print("❌ API request timeout")
        return []
    except requests.exceptions.ConnectionError:
        print("❌ Failed to connect to API")
        return []
    except Exception as e:
        print(f"❌ Error fetching data from API: {e}")
        return []

def get_mapping_vendor_name():
    """
    ฟังก์ชันสำหรับดึงข้อมูลจาก API
    
    Returns:
        list: รายการข้อมูลที่ดึงมาจาก API
    """
    try:
        # กำหนด URL ของ API
        api_url = "https://cnexrwsphsqdykauuaga.supabase.co/rest/v1/mapping_vendor_name"
        # กำหนด headers สำหรับ request
        headers = {
            'Content-Type': 'application/json',
            'apiKey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg',
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNuZXhyd3NwaHNxZHlrYXV1YWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNjYwODcsImV4cCI6MjA3MTg0MjA4N30.lYYJexUI1Lj_EWz0jQ0ROZV0_pLVGrtLNIPBEDavcPg'
        }
        
        # ส่ง GET request ไปยัง API
        response = requests.get(api_url, headers=headers, timeout=30)
        
        # ตรวจสอบ status code
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Successfully fetched {len(data)} records from API")
            return data
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return []
            
    except requests.exceptions.Timeout:
        print("❌ API request timeout")
        return []
    except requests.exceptions.ConnectionError:
        print("❌ Failed to connect to API")
        return []
    except Exception as e:
        print(f"❌ Error fetching data from API: {e}")
        return []

async def main(reference_number: str):

    mapping_type = [
        {"value":"1", "label": "food_registry_fallback"},
        {"value":"2", "label": "cosmetic_registry"},
        {"value":"3", "label": "วัตถุอันตราย"},
        {"value":"4", "label": "pharmaceutical_registry"},
        {"value":"5", "label": "ยาเสพติด"},
        {"value":"6", "label": "medical_registry"},
        {"value":"7", "label": "สมุนไพร"},
    ]

    print("🚀 Starting FDA MOPH Complete Login Automation...")

    print(f"🔍 Reference Number: {reference_number}")

    data = get_extracted_data_requests(reference_number)
    job = get_jobs_data_requests(reference_number)
    mapping_vendor_name = get_mapping_vendor_name()

    # แปลง updated_at เป็น datetime
    for row in data:
        row["updated_at"] = datetime.fromisoformat(row["updated_at"])

    # เอาเวลาของตัวสุดท้ายเป็น reference
    latest_time = data[0]["updated_at"]
    print(f"Latest time: {latest_time}")
    five_minutes_before = latest_time - timedelta(minutes=5)

    # กรองเฉพาะข้อมูลที่อยู่ในช่วง 5 นาทีสุดท้ายจาก latest_time
    recent_data = [row for row in data if row["updated_at"] >= five_minutes_before]

    recent_data = sorted(recent_data, key=lambda x: x["reference_number"], reverse=True)

    grouped = {}

    for row in recent_data:
        reference_number = row["reference_number"]
        invoice_number = row["invoice_number"]
        product_code = row["product_code"]
        qty = row["qty"]

        # --- group ตาม reference_number ---
        if reference_number not in grouped:
            grouped[reference_number] = {
                "reference_number": reference_number,
                "items": []
            }
        ref_items = grouped[reference_number]["items"]

        # --- group ตาม invoice_number ---
        invoice = next((i for i in ref_items if i["invoice_number"] == invoice_number), None)
        if not invoice:
            invoice = {"invoice_number": invoice_number, "items": []}
            ref_items.append(invoice)

        # --- group ตาม item_code ---
        item = next((it for it in invoice["items"] if it["product_code"] == product_code and it["qty"] == qty), None)
        if not item:
            item = {"product_code": product_code, "qty": qty, "items": []}
            invoice["items"].append(item)

        # push row (ยกเว้น key ที่ใช้เป็น group)
        rest = {k: v for k, v in row.items() if k not in ["reference_number", "invoice_number", "product_code", "qty"]}
        item["items"].append(rest)

    # แปลง dict → list
    grouped_list = list(grouped.values())

    for ref in grouped_list:
        ref["items"].sort(key=lambda x: x["invoice_number"])
    # Launch browser
    browser = await uc.start(
        headless=False,
        browser_args=[
            "--window-size=1920,1080",
            "--start-maximized",
        ],
    )
    input_data = []
    license_list = []

    license_list = job[0]["license_item"]
    stepJob = job[0]["step"]
    input_data = stepJob["step2"]

    data_permit_group = []
    # ดึงเฉพาะฟิลด์ที่ต้องการและเอาค่าที่ไม่ซ้ำกัน
    data_permit_group = []
    seen = set()

    for item in data:
        # สร้าง tuple เพื่อเช็คความซ้ำ
        key = (item['permit_id'], item['permit_type'], item['vendor_name'], item['product_code'])
        
        if key not in seen:
            seen.add(key)
            data_permit_group.append({
                'permit_id': item['permit_id'],
                'permit_type': item['permit_type'],
                'vendor_name': item['vendor_name'],
                'product_code': item['product_code']
            })

    if stepJob["step1"] != "success" :

        print("🌐 Opening Digital ID login page...")
        page = await browser.get("https://privus.fda.moph.go.th/")
        
        # เริ่ม background task ตรวจ dialog
        asyncio.create_task(monitor_dialogs(page))

        entrepreneur_click = await click_selector_with_retry(page, "ผู้ประกอบการ", max_retries=3, wait_time=2, button='left', click_count=2)
        # entrepreneur_click = await click_with_retry(page, "ผู้ประกอบการ", max_retries=3, wait_time=2)
        if not entrepreneur_click:
            print("❌ Failed to click ผู้ประกอบการ")

        digital_id_click = await click_selector_with_retry(page, "Digital ID", max_retries=3, wait_time=2, button='left', click_count=2)
        # digital_id_click = await click_with_retry(page, "Digital ID", max_retries=3, wait_time=2)
        if not digital_id_click:
            print("❌ Failed to click Digital ID")

        if page.url == "https://privus.fda.moph.go.th/Frm_authorize.aspx":
            print("✅ Already on Digital ID page")
        else:
            # ใช้งานฟังก์ชัน
            success_username = await input_with_retry(
                page, 
                'input[placeholder*="บัญชีผู้ใช้งาน"], input[placeholder*="เลขประจำตัวประชาชน"]',
                "1100400181573",
                field_name="Username",
                max_retries=3,
                wait_time=2
            )

            if not success_username:
                print("❌ Failed to input username")

            success_password = await input_with_retry(
                page,
                'input[placeholder*="รหัสผ่าน"], input[type="password"]',
                "imt19790000",
                field_name="Password",
                max_retries=3,
                wait_time=2
            )

            if not success_password:
                print("❌ Failed to input password")

            # Handle cookie banner
            allow_all_click = await click_selector_with_retry(page, "ยอมรับทั้งหมด", max_retries=3, wait_time=2, button='left', click_count=2)
            # allow_all_click = await click_with_retry(page, "ยอมรับทั้งหมด", max_retries=3, wait_time=2)
            if not allow_all_click:
                print("❌ Failed to click ยอมรับทั้งหมด")

            close_click = await click_selector_with_retry(page, "ปิด", max_retries=3, wait_time=2, button='left', click_count=2)
            # close_click = await click_with_retry(page, "ปิด", max_retries=3, wait_time=2)
            if not close_click:
                print("❌ Failed to click ปิด")

            # Take screenshot before login
            await page.save_screenshot("02-before-login.png")
            print("📸 Screenshot saved: 02-before-login.png")

            login_click = await click_selector_with_retry(page, "เข้าสู่ระบบ", max_retries=3, wait_time=2, button='left', click_count=2)
            # login_click = await click_with_retry(page, "เข้าสู่ระบบ", max_retries=3, wait_time=2)
            if not login_click:
                print("❌ Failed to click เข้าสู่ระบบ")

            # Wait for login to complete
            print("⏳ Waiting for login to complete...")

            # Take screenshot after login
            await page.save_screenshot("03-after-login.png")
            print("📸 Screenshot saved: 03-after-login.png")

            # Check final URL
            final_url = page.url
            print(f"\n📍 Final URL: {final_url}")

            # Get page title
            title = await page.evaluate("document.title")
            print(f"📄 Page title: {title}")

            # Check if login was successful
            if "privus.fda.moph.go.th" in final_url:
                success_text_capcha = await text_with_retry(page, "You failed the CAPTCHA", max_retries=1, wait_time=2)

                if success_text_capcha:
                    success_password = await input_with_retry(
                        page,
                        'input[placeholder*="รหัสผ่าน"], input[type="password"]',
                        "imt19790000",
                        field_name="Password",
                        max_retries=3,
                        wait_time=2
                    )

                    if not success_password:
                        print("❌ Failed to input password")

                    login_click = await click_selector_with_retry(page, "เข้าสู่ระบบ", max_retries=3, wait_time=2, button='left', click_count=2)
                    # login_click = await click_with_retry(page, "เข้าสู่ระบบ", max_retries=3, wait_time=2)
                    if not login_click:
                        print("❌ Failed to click เข้าสู่ระบบ")

                    success_text_capcha = await text_with_retry(page, "You failed the CAPTCHA", max_retries=2, wait_time=2)

                    if success_text_capcha:
                        success_password = await input_with_retry(
                            page,
                            'input[placeholder*="รหัสผ่าน"], input[type="password"]',
                            "imt19790000",
                            field_name="Password",
                            max_retries=3,
                            wait_time=2
                        )

                        if not success_password:
                            print("❌ Failed to input password")

                        login_click = await click_selector_with_retry(page, "เข้าสู่ระบบ", max_retries=3, wait_time=2, button='left', click_count=2)
                        # login_click = await click_with_retry(page, "เข้าสู่ระบบ", max_retries=3, wait_time=2)
                        if not login_click:
                            print("❌ Failed to click เข้าสู่ระบบ")

                print("\n✅ Login successful! Redirected to FDA system")
            elif "error" in final_url.lower():
                print("\n❌ Login failed - error in URL")
            else:
                print(f"\n⚠️ Unexpected URL: {final_url}")

        countinvoice = len(data_permit_group)
        countlicense = 0

        for data_permit in data_permit_group:
            if(len(license_list) != countinvoice):
                target = {
                    "permit_id": data_permit["permit_id"],
                    "product_code": data_permit["product_code"]
                }

                exists = any(
                    all(row[key] == value for key, value in target.items())
                    for row in license_list
                )

                if not exists:
                    # Find customer name
                    print("📝 Finding customer name")
                    thai_name = next(
                        (item["vendor_name_thai"] for item in mapping_vendor_name if item["vendor_name_eng"] == data_permit["vendor_name"]),
                        None
                    )
                    GlobalState.company_name = thai_name

                    print(f"📝 Customer name: {GlobalState.company_name}")

                    if(page.url != "https://importlpi.fda.moph.go.th/SIP/Frm_ConvertCode.aspx"):
                        success_click_customer = await click_input_with_retry(
                            page,
                            f'input[type="submit"][value*="{GlobalState.company_name}"]',
                            field_name=f"Customer: {GlobalState.company_name}",
                            max_retries=3,
                            wait_time=2,
                            click_count=2
                        )

                        if not success_click_customer:
                            print(f"❌ Cannot proceed - failed to click customer: {GlobalState.company_name}")

                    if(page.url != "https://importlpi.fda.moph.go.th/SIP/Frm_ConvertCode.aspx"):
                        success_click_license_per_invoice = await click_input_with_retry(
                            page,
                            f'input[type="submit"][value="License per Invoice"]', 
                            field_name=f"License Per Invoice",
                            max_retries=3,
                            wait_time=2,
                            click_count=2
                        )

                        if not success_click_license_per_invoice:
                            print(f"❌ Cannot proceed - failed to click License per Invoice")

                    # Find button Convert Code
                    if(page.url != "https://importlpi.fda.moph.go.th/SIP/Frm_ConvertCode.aspx"):
                        print("📝 Finding Convert Code")
                        convert_code_click = await click_selector_with_retry(
                            page, 
                            f'a[href="Frm_ConvertCode.aspx"]',
                            button='left',
                            click_count=2
                        )

                        if not convert_code_click:
                            print("❌ Cannot proceed - failed to click Convert Code")
                            
                    await action_sky_net(page, data_permit, license_list, input_data, invoice_number, stepJob, mapping_type)

                    countlicense = len(license_list)

                    if countlicense == countinvoice:
                        stepJob["step1"] = "success"
                    elif countlicense > 0:
                        stepJob["step1"] = "process"
                    else:
                        stepJob["step1"] = "fail"
                    
                    payload = {
                        "license_item": license_list,
                        "step": stepJob
                    }

                    update_step_job(reference_number, payload)
                    await take_screenshot(page, "step_get_license_" + invoice_number + "_" + data_permit["product_code"], reference_number)
                    await asyncio.sleep(1)

    # *****NETBAY*****
    imtpage = await browser.get("https://imtl.nbgwhosting.com/imtl/SPN/")
    print(f"📍 URL: {imtpage.url}")

    # *****Login NETBAY*****
    # Find and fill username Net Bay field
    print("📝 Entering username Net Bay...")

    success_username_netbay = await input_with_retry(
        imtpage, 
        'input[name*="USERNAME"], input[id*="user"]',
        "TEST",
        field_name="Username Net Bay",
        max_retries=3,
        wait_time=2
    )

    if not success_username_netbay:
        print("❌ Failed to enter username Net Bay")

    # Find and fill password Net Bay field
    print("📝 Entering password Net Bay...")
    success_password_netbay = await input_with_retry(
        imtpage, 
        'input[name*="PASSWORD"], input[id*="passwd"], input[type="password"]',
        "0000",
        field_name="Password Net Bay",
        max_retries=3,
        wait_time=2
    )

    if not success_password_netbay:
        print("❌ Failed to enter password Net Bay")

    # Find button login Net Bay
    print("🔘 button login Net Bay...")
    success_click_login_netbay = await click_input_with_retry(
        imtpage,
        'img[usemap*="#Map"]',
        field_name="login Net Bay",
        max_retries=3,
        wait_time=2,
        click_count=2
    )
    
    if not success_click_login_netbay:
        print(f"❌ Cannot proceed - failed to click login Net Bay")
        
    imtpage1 = None
    imtpage2 = None
    imtpage3 = None

    existing_tabs = browser.tabs

    # Restricted Goods Permit
    print("🔘 Click Restricted Goods Permit")

    success_restricted_goods_permit_netbay_click = await click_selector_with_retry(
        imtpage, 
        "Restricted Goods Permit", 
        max_retries=3, 
        wait_time=2, 
        button='left', 
        click_count=2)
    # success_restricted_goods_permit_netbay_click = await click_with_retry(
    #     imtpage,
    #     "Restricted Goods Permit",
    #     max_retries=3,
    #     wait_time=2,
    # )

    if success_restricted_goods_permit_netbay_click:
        # หา tab ใหม่
        new_tabs = [tab for tab in browser.tabs if tab not in existing_tabs]
        if new_tabs:
            imtpage1 = new_tabs[0]
            print("✅ Popup tab ready:", imtpage1.url)
            await asyncio.sleep(1)
        else:
            print("⚠️ No new tab found after clicking")
    else:
        print("❌ Cannot proceed - failed to click Restricted Goods Permit")
    
    while imtpage1 is None:
        await asyncio.sleep(1)
    print("✅ Popup tab ready:", imtpage1.url)

    for group in grouped_list:
        invoice_items = []
        await asyncio.sleep(1)

        # select BY
        print("🔘 Select BY")
        success_select_by = await select_dropdown_with_retry(
            imtpage1,
            selector='select[name="BY"], select[id="BY"]',
            value="restrictedgoodsdetail.declReference",
            label="BY",
            max_retries=3,
            wait_time=2
        )

        if not success_select_by:
            print("⚠️ Cannot proceed - failed to select BY")
        
        print("📝 search reference number")
        success_invoice_input = await fill_input_with_retry(
            imtpage1,
            selector='input[name="txtSearch"], input[id="txtSearch"]',
            value=group["reference_number"],
            label="Invoice",
            max_retries=3,
            wait_time=2
        )

        if not success_invoice_input:
            print("⚠️ ไม่สามารถกรอก Invoice ได้")
            
        # click bitton search
        print("🔘 Click Button Search reference")
        success_search_reference_netbay_click = await click_selector_with_retry(
            imtpage1, 
            'button[name="btnSearch"], button[id="btnSearch"]',
            button='left',
            click_count=1
        )

        if not success_search_reference_netbay_click:
            print("❌ Cannot proceed - failed to click Se")

        # await asyncio.sleep(5)

        for invoice in group["items"]:
            print("Invoice Number:", invoice["invoice_number"])
            invoice_to_check = invoice["invoice_number"]

            print("🔍 Checking invoice:", invoice_to_check)
            # ดึง list ของ step2 ออกมาก่อน
            step2_list = stepJob.get("step2", [])

            # ตรวจสอบว่ามี invoice ที่ตรงและ status เป็น complete หรือไม่
            has_complete = any(
                item.get("invoice_number") == invoice_to_check and item.get("status") == "success" and item.get("user_data_status") == "success"
                for item in step2_list
            )
            print(has_complete)

            if has_complete:
                continue
            else:
                try:
                    # ✅ เพิ่มส่วนนี้: ตรวจสอบว่ามี invoice_items ไหนยังไม่ success มั่ง
                    incomplete_items = []
                    for step2_item in step2_list:
                        if step2_item.get("invoice_number") == invoice_to_check:
                            invoice_items = step2_item.get("invoice_items", [])
                            for item in invoice_items:
                                if item.get("status") != "success":
                                    incomplete_items.append(item["item_code"])

                    if incomplete_items:
                        print(f"⚠️ Invoice {invoice_to_check} ยังมี items ที่ไม่ success: {incomplete_items}")
                    else:
                        print(f"✅ Invoice {invoice_to_check} ไม่มี items ค้างอยู่ (หรือยังไม่ถูกสร้างใน step2)")

                    clickedReferenceEdit = await imtpage1.evaluate(f'''
                        (() => {{
                            const table = document.querySelector('table#list_main');
                            if (!table) return false;
                            
                            const rows = table.querySelectorAll('tbody tr');
                            
                            for (let i = 0; i < rows.length; i++) {{
                                const cells = rows[i].querySelectorAll('td');
                                if (cells.length >= 8) {{
                                    const reference_number = cells[10]?.textContent?.trim() || '';
                                    const invoiceNumber = cells[8]?.textContent?.trim() || '';
                                    
                                    if (reference_number === '{reference_number}' && invoiceNumber === '{invoice["invoice_number"]}') {{
                                        // เจอแล้ว - คลิกปุ่ม Edit
                                        const editButton = rows[i].querySelector('li[title="Edit"] a');
                                        // if (editButton) {{
                                        //     editButton.click();
                                        //     return true;
                                        // }}
                                        if (editButton) {{
                                            const href = editButton.getAttribute('href');
                                            window.open(href, '_blank');
                                            return true;
                                        }}
                                    }}
                                }}
                            }}
                            return false;
                        }})()
                    ''')

                    if clickedReferenceEdit:
                        invoicenumber = invoice["invoice_number"]
                        invoice_number = invoice["invoice_number"]
                        print(f"✅ Clicked link for invoice {invoicenumber}")
                        # await asyncio.sleep(2)
                        
                        # สลับไป tab ใหม่
                        new_tabs = [tab for tab in browser.tabs if tab not in existing_tabs]
                        if new_tabs:
                            imtpage2 = new_tabs[-1]  # ใช้ tab สุดท้าย ไม่ใช่ index 1
                            print("✅ Popup tab ready:", imtpage2.url)
                    else:
                        url = imtpage1.url
                        parsed = urlparse(url)
                        params = parse_qs(parsed.query)
                        action_value = params.get("ACTION", [None])[0]
                        if action_value != "create_from_spn":
                            # SPN Click
                            print("🔘 Click SPN")
                            success_spn_click = await click_selector_with_retry(
                                imtpage1, 
                                'button#btnNewSPN, button[name="btnNewSPN"]',
                                button='left',
                                click_count=1
                            )

                            if not success_spn_click:
                                print("❌ Cannot proceed - failed to click SPN")

                            # Input Reference Number
                            print("🔘 Input Reference")
                            ref_no = group["reference_number"]
                            success_reference_input = await fill_input_with_retry(
                                imtpage1,
                                selector='input[name*="referenceNo"], input[id*="referenceNo"]',
                                value=ref_no,
                                label="Reference No Net Bay",
                                max_retries=3,
                                wait_time=2
                            )

                            if not success_reference_input:
                                print("⚠️ Failed to input Reference No Net Bay")

                            # select authorityTaxSel
                            print("🔘 Select authority Tax Sel")
                            success_select_authorityTaxSel = await select_dropdown_with_retry(
                                imtpage1,
                                selector='select[name*="authorityTaxSel"], select[id*="authorityTaxSel"]',
                                value="0994000165676",
                                label="Authority Tax Sel",
                                max_retries=3,
                                wait_time=2
                            )

                            if not success_select_authorityTaxSel:
                                print("⚠️ Failed to select Authority Tax Sel")
                        
                            # click bitton search
                            print("🔘 Click Button Search")
                            search_click = await click_selector_with_retry(
                                imtpage1, 
                                'button[name*="btnSearch"], button[id*="btnSearch"], input[type="button"]',
                                button='left',
                                click_count=1
                            )

                            if not search_click:
                                print("❌ Cannot proceed - failed to click button Search")

                        print("Invoice:", invoice["invoice_number"])
                        invoice_number = invoice["invoice_number"]
                        # Click all checkboxes using JavaScript
                        print("🔘 Check box invoice")
                        try:
                            await imtpage1.evaluate(f'''
                                document.querySelectorAll('input[data-invoiceno="{invoice_number}"]').forEach(cb => {{
                                    if (!cb.checked) cb.click();
                                }});
                            ''')
                            
                            print("✅ Selected checkboxes for invoice " + invoice_number)

                            # Step 2: Get invoice items
                            invoice_items_raw = await imtpage1.evaluate(f'''
                                (() => {{
                                    const items = [];
                                    document.querySelectorAll('input[data-invoiceno="{invoice_number}"]:checked').forEach(cb => {{
                                        const row = cb.closest('tr');
                                        const invoiceItemCell = row.querySelector('td[data-invoiceitem]');
                                        if (invoiceItemCell) {{
                                            items.push(invoiceItemCell.getAttribute('data-invoiceitem'));
                                        }}
                                    }});
                                    return items;
                                }})()
                            ''')

                            invoice_items = [item['value'] for item in invoice_items_raw]
                            
                            print("📋 Invoice Items:", invoice_items)
                            await asyncio.sleep(0.5)

                        except Exception as e:
                            print(f"❌ Error checking boxes: {e}")
                                    
                        # click button Create Reference
                        print("🔘 Click Create Reference")
                        create_reference_click = await click_selector_with_retry(
                            imtpage1, 
                            'button[id*="createRgpbtn2"]',
                            button='left',
                            click_count=1
                        )

                        if not create_reference_click:
                            print("❌ Cannot proceed - failed to click button Search")

                        # select License Type
                        print("🔘 Select License Type")
                        success_select_license_type = await select_dropdown_with_retry(
                            imtpage1,
                            selector='select[name*="req_licenseType"], select[id*="licenseTypeTxt"]',
                            value="0",
                            label="License Type",
                            max_retries=3,
                            wait_time=2
                        )

                        if not success_select_license_type:
                            print("⚠️ Failed to select License Type")
                        
                        # click button Create Reference
                        print("🔘 Click Confirm Create Reference")
                        confirm_create_ref_click = await click_selector_with_retry(
                            imtpage1, 
                            'button[id*="SubmitInitBt"]',
                            button='left',
                            click_count=1
                        )

                        if not confirm_create_ref_click:
                            print("❌ Cannot proceed - failed to click button Search")
                        else:
                            result = [
                                {
                                    "item_code": code,
                                    "license_number": "",
                                    "product_items": [],
                                    "status": "pending",
                                    "remark": "",
                                    "remark_product": ""
                                }
                                for code in invoice_items
                            ]

                            input_data.append({
                                "invoice_number": invoice_number,
                                "status": "process",
                                "user_data_status": "process",
                                "invoice_items": result,
                            })

                            stepJob['step2'] = input_data

                            payload = {
                                "step": stepJob
                            }

                            update_step_job(reference_number, payload)
                            await asyncio.sleep(1)

                            for step2_item in input_data:
                                if step2_item.get("invoice_number") == invoice_to_check:
                                    invoice_items = step2_item.get("invoice_items", [])
                                    for item in invoice_items:
                                        if item.get("status") != "success":
                                            incomplete_items.append(item["item_code"])

                        # click OK
                        print("🔘 Click OK")
                        confirm_create_ref_click = await click_selector_with_retry(
                            imtpage1, 
                            "OK", 
                            max_retries=3, 
                            wait_time=2, 
                            button='left', 
                            click_count=2)
                        # confirm_create_ref_click = await click_with_retry(imtpage1, "OK", max_retries=3, wait_time=2)
                        if not confirm_create_ref_click:
                            print("❌ Failed to click เข้าสู่ระบบ")

                        invoice_no = invoice_number  # เปลี่ยนได้ตามต้องการ
                        await take_screenshot(imtpage1, "step_create_invoiceNumber_" + invoice_no, reference_number)

                        print(f"🔘 Click first link for invoice {invoice_no}")
                        try:
                            result = await imtpage1.evaluate(f'''
                                (() => {{
                                    const row = document.querySelector('tr:has(input[data-invoiceno="{invoice_no}"])');
                                    if (row) {{
                                        const link = row.querySelector('td:last-child a');
                                        if (link) {{
                                            link.click();
                                            return true;
                                        }}
                                    }}
                                    return false;
                                }})()
                            ''')
                            
                            if result:
                                print(f"✅ Clicked link for invoice {invoice_no}")
                                # await asyncio.sleep(2)
                                
                                # สลับไป tab ใหม่
                                new_tabs = [tab for tab in browser.tabs if tab not in existing_tabs]
                                if new_tabs:
                                    imtpage2 = new_tabs[-1]  # ใช้ tab สุดท้าย ไม่ใช่ index 1
                                    print("✅ Popup tab ready:", imtpage2.url)
                            else:
                                print(f"ℹ️ No link found for invoice {invoice_no}")
                                
                        except Exception as e:
                            print(f"❌ Error: {e}")
                except Exception as e:
                    print(f"❌ Error clicking link: {e}")

                while imtpage2 is None:
                    await asyncio.sleep(2)
                print("✅ Popup tab ready:", imtpage2.url)

                checkStepJobUserData = None

                for item in stepJob["step2"]:
                    if item['invoice_number'] == invoice_number:
                        checkStepJobUserData = item
                        break

                if checkStepJobUserData["user_data_status"] != "success":
                    # Input ID CARD ผู้แจ้ง
                    print("🔘 Input ID CARD ผู้แจ้ง")
                    idCard_inputNetBay = await fill_input_with_retry(
                        imtpage2,
                        selector='input[name*="ins_informantIDCardNumber"], input[id*="CTRinformantIDCardNumber"]',
                        value="1100400181573",
                        label="ID CARD ผู้แจ้ง Net Bay",
                        max_retries=3,
                        wait_time=2
                    )

                    if not idCard_inputNetBay:
                        print("⚠️ Failed to input ID CARD ผู้แจ้ง Net Bay")
                    
                    # Input ชื่อผู้แจ้ง
                    print("🔘 Input ชื่อผู้แจ้ง")
                    nameCard_inputNetBay = await fill_input_with_retry(
                        imtpage2,
                        selector='input[name="ins_informantName"], input[id="CTRinformantName"]',
                        value="น.ส. มนันยา วันทนียกุล",
                        label="ชื่อผู้แจ้ง",
                        max_retries=3,
                        wait_time=2
                    )

                    if not nameCard_inputNetBay:
                        print("⚠️ Failed to input ชื่อผู้แจ้ง")

                    # Input รหัสผู้รับมอบอำนาจ
                    print("🔘 Input รหัสผู้รับมอบอำนาจ")
                    attorneyIDCard_inputNetBay = await fill_input_with_retry(
                        imtpage2,
                        selector='input[name*="ins_attorneyIDCard"], input[id*="CTRattorneyIDCard"]',
                        value="1100400181573",
                        label="รหัสผู้รับมอบอำนาจ",
                        max_retries=3,
                        wait_time=2
                    )

                    if not attorneyIDCard_inputNetBay:
                        print("⚠️ Failed to input รหัสผู้รับมอบอำนาจ")
                    
                    # Input ประเทศปลายทาง
                    print("🔘 Input ประเทศปลายทาง")
                    destinationCountryCode_inputNetBay = await fill_input_with_retry(
                        imtpage2,
                        selector='input[name*="ins_destinationCountryCode"], input[id*="CTRdestinationCountryCode"]',
                        value="TH",
                        label="รหัสผู้รับมอบอำนาจ",
                        max_retries=3,
                        wait_time=2
                    )

                    if not destinationCountryCode_inputNetBay:
                        print("⚠️ Failed to input รหัสผู้รับมอบอำนาจ")
                    
                    # click Save
                    print("🔘 click Save")
                    saveBTN_inputNetBay = await click_selector_with_retry(
                        imtpage2, 
                        'input[name*="saveBTN"], input[id*="saveBTN"], input[type="image"], input[title="F12 [Save]"]',
                        button='left',
                        click_count=1
                    )

                    if saveBTN_inputNetBay: 
                        update_input_data(input_data, invoice_number, "", 9, "", "process", "", 0, stepJob, reference_number, "", "")
                        await take_screenshot(imtpage2, "step_userData_" + invoice_number, reference_number)

                        # await asyncio.sleep(4)
                    else: 
                        print("ℹ️  No click Save field found")

                # list invoice number
                for idx, detail in enumerate(invoice["items"], start=1):
                    print("🔘 List Invoice Number")
                    item_code = ""
                    try:
                        print(f'{idx}:{invoice_number}')
                        invoice_number_click = await imtpage2.find(
                            f'//span[contains(@class, "oSpanInvoice") and contains(normalize-space(.), "{idx}:{invoice_number}")]',
                            timeout=5,
                        )
                        if invoice_number_click:
                            
                            # ดึงค่า text จาก element
                            span_text = invoice_number_click.text
                            item_code = span_text.split('-')[-1]

                            await invoice_number_click.mouse_click(str, 2)
                            # await asyncio.sleep(0.5)
                            print("✅ Invoice number clicked")
                            await asyncio.sleep(1)
                        else:
                            print("ℹ️  No invoice number to click")
                    except Exception as e:
                        print(f"❌ Error clicking invoice number: {e}")

                    invoiceItemsStatus = None

                    for item in checkStepJobUserData["invoice_items"]:
                        if item['item_code'] == item_code:
                            invoiceItemsStatus = item
                            break

                    license_number = ""
                    real_value = ""
                    productCode_value = ""
                    if invoiceItemsStatus["status"] != "success":

                        print("Click Product Code in Invoice number")
                        try: 
                            productCode_click = await imtpage2.find(
                                'span[id="productCodelink"]',
                                timeout=5,
                            )
                            if productCode_click:
                                # เก็บ targets เดิม
                                existing_targets = list(browser.targets)

                                await productCode_click.click()

                                # รอ target ใหม่
                                await asyncio.sleep(2)
                                # หา target ใหม่โดยเปรียบเทียบ list
                                current_targets = list(browser.targets)
                                new_targets = [t for t in current_targets if t not in existing_targets]
                                
                                if new_targets:
                                    # ใช้ target ใหม่โดยตรง (มันเป็น Tab object อยู่แล้ว)
                                    imtpage3 = new_targets[0]
                                    await imtpage3  # รอให้โหลดเสร็จ
                                    print(f"✅ New window ready: {imtpage3.url}")
                                else:
                                    print("⚠️ No new target found, using latest tab")
                                    imtpage3 = browser.tabs[-1]
                                    await imtpage3
                                    print(f"✅ Using latest tab: {imtpage3.url}")
                            else:
                                print("ℹ️  No product code to click")

                        except Exception as e:
                            print(f"❌ Error Get Product in Invoice number: {e}")

                        print("Get Product Code in Invoice number")
                        try: 
                            productCode_value = await imtpage3.evaluate('document.querySelector(\'input[name="ins_productCode"]\').value')
                            
                            await imtpage3.close()
                            await asyncio.sleep(1)

                        except Exception as e:
                            print(f"❌ Error Get QTY in Invoice number: {e}")

                        try: 
                            # วิธีที่ 1: ใช้ querySelector และ getAttribute
                            real_value = await imtpage2.evaluate('''
                                document.querySelector('#ITMquantity').getAttribute('realvalue')
                            ''')

                        except Exception as e:
                            print(f"❌ Error Get QTY in Invoice number: {e}")
                        
                        filtered_data = [item for item in data if item["product_code"] == productCode_value and float(item["qty"]) == float(real_value)]
                        
                        remark_product = next(
                            (item["remark_product"] for item in license_list
                            if item["permit_id"] == filtered_data[0]["permit_id"] and item["product_code"] == productCode_value),
                            None
                        )

                        remark = next(
                            (item["remark"] for item in license_list
                            if item["permit_id"] == filtered_data[0]["permit_id"] and item["product_code"] == productCode_value),
                            None
                        )

                        if(remark_product != None):
                            if invoiceItemsStatus["remark_product"] == "":
                                # Input Remark
                                print("🔘 Input Remark Product")
                                remark_inputNetBay = await fill_input_with_retry(
                                    imtpage2,
                                    selector='textarea[name="ins_characteristic"], input[id="ITMcharacteristic"]',
                                    value=remark_product,
                                    label="Remark Product",
                                    max_retries=3,
                                    wait_time=2
                                )

                                if not remark_inputNetBay:
                                    print("❌ Input Remark Product ล้มเหลว")
                        
                        if remark != None:
                            if invoiceItemsStatus["remark"] == "":
                                print("🔘 Input Remark")
                                ins_remark_input = await fill_input_with_retry(
                                    imtpage2,
                                    selector='textarea[name="ins_remark"], input[id="ITMremark"]',
                                    value=remark,
                                    label="Remark",
                                    max_retries=3,
                                    wait_time=2
                                )

                                if not ins_remark_input:
                                    print("❌ Input Remark Product ล้มเหลว")

                        if invoiceItemsStatus["remark_product"] == "" or invoiceItemsStatus["remark"] == "":
                            # click Save
                            print("🔘 click Save")
                            saveBTN_input_remarkNetBay = await click_selector_with_retry(
                                imtpage2, 
                                'input[id*="saveInvoiceBTN"]',
                                button='left',
                                click_count=1
                            )

                            if saveBTN_input_remarkNetBay: 
                                await asyncio.sleep(1)
                                update_input_data(input_data, invoice_number, item_code, 1, license_number, "process", "", len(detail["items"]), stepJob, reference_number, remark, remark_product)
                                await take_screenshot(imtpage2, "step_remark_" + invoice_number + "_" + item_code, reference_number)

                                # await asyncio.sleep(3)
                                print("🔘 List Invoice Number")
                                try:
                                    invoice_number_click = await imtpage2.find(
                                        f'//span[contains(@class, "oSpanInvoice") and contains(normalize-space(.), "{idx}:{invoice_number}")]',
                                        timeout=5,
                                    )

                                    if invoice_number_click:
                                        await invoice_number_click.mouse_click(str, 2)
                                        # await asyncio.sleep(0.5)
                                        print("✅ Invoice number clicked")
                                        await asyncio.sleep(1)
                                    else:
                                        print("ℹ️  No invoice number to click")
                                except Exception as e:
                                    print(f"❌ Error clicking invoice number: {e}")
                            else:
                                print("ℹ️  No click Save field found")

                        # await asyncio.sleep(3)

                        # ⭐ รอให้ iframe และ input field พร้อมก่อนกรอกข้อมูล
                        print("⏳ Waiting for iframe and input to be ready...")
                        iframe_ready = False
                        for attempt in range(20):  # รอสูงสุด 10 วินาที
                            try:
                                input_exists = await imtpage2.evaluate('''
                                    (() => {
                                        const iframe = document.querySelector('#detail3TabsFrm');
                                        if (!iframe) return false;
                                        
                                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                        if (!iframeDoc) return false;
                                        
                                        const input = iframeDoc.querySelector('#Author-licenseNumber');
                                        return input && input.offsetParent !== null;
                                    })()
                                ''')
                                
                                if input_exists:
                                    iframe_ready = True
                                    print("✅ Iframe and input field are ready!")
                                    break
                            except Exception as e:
                                print(f"⚠️ Attempt {attempt + 1}: {e}")
                            
                            await asyncio.sleep(0.5)
                        
                        if not iframe_ready:
                            print("❌ Iframe/input not ready after waiting, skipping this record")
                            continue  # ข้ามไป record ถัดไป
                        
                        # ⭐ เคลียร์ค่าเก่าก่อนกรอกใหม่

                        if invoiceItemsStatus["license_number"] == "":

                            license_number = next(
                                (item["license_number"] for item in license_list
                                if item["permit_id"] == filtered_data[0]["permit_id"] and item["product_code"] == productCode_value),
                                ""
                            )

                            if license_number != "":
                                print("📝 Filling license number...")
                                try:
                                    await imtpage2.evaluate(f'''
                                        (() => {{
                                            const iframe = document.querySelector('#detail3TabsFrm');
                                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                            const input = iframeDoc.querySelector('#Author-licenseNumber');
                                            
                                            if (input) {{
                                                // ⭐ เคลียร์ค่าเก่า
                                                input.value = '';
                                                input.focus();
                                                
                                                // รอนิดนึง
                                                setTimeout(() => {{
                                                    // ⭐ ใส่ค่าใหม่
                                                    input.value = '{license_number}';
                                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                                }}, 100);
                                                
                                                return true;
                                            }} else {{
                                                return false;
                                            }}
                                        }})()
                                    ''')

                                    print("✅ License number entered")
                                    await asyncio.sleep(1)
                                except Exception as e:
                                    print(f"❌ Error entering license number: {e}")
                                    continue  # ข้ามไป record ถัดไป
                                
                                
                                # คลิกปุ่ม Save
                                print("🔘 Clicking Save button")
                                await imtpage2.evaluate('''
                                    (() => {{
                                        const iframe = document.querySelector('#detail3TabsFrm');
                                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                        const saveButton = iframeDoc.querySelector('#Author-save');
                                        if (saveButton) {{
                                            saveButton.click();
                                            console.log('Button clicked');
                                        }}
                                    }})()
                                ''')

                                update_input_data(input_data, invoice_number, item_code, 2, license_number, "process", "", len(detail["items"]), stepJob, reference_number, remark, remark_product)
                                await take_screenshot(imtpage2, "step_licesenseNumber_" + invoice_number + "_" + item_code, reference_number)

                                print("✅ Button Save clicked")
                                # await asyncio.sleep(3)

                        if len(filtered_data) != len(invoiceItemsStatus["product_items"]):

                            # คลิกTab
                            print("🔘 Clicking Tab")
                            await imtpage2.evaluate('''
                                (() => {{
                                    const iframe = document.querySelector('#detail3TabsFrm');
                                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                    const clickTab = iframeDoc.querySelector('a[href="#SubDetailtabs-2"]');
                                    if (clickTab) {{
                                        clickTab.click();
                                        console.log('button clicked');
                                    }}
                                }})()
                            ''')

                            print("✅ Tab clicked")
                            await asyncio.sleep(1)

                            # ⭐ รอให้ input field ปรากฏ (ใช้ loop แทน wait_for_function)
                            print("⏳ Waiting for input field to be ready...")
                            input_ready = False
                            for attempt in range(20):  # รอสูงสุด 10 วินาที (20 * 0.5)
                                try:
                                    input_exists = await imtpage2.evaluate('''
                                        (() => {
                                            const iframe = document.querySelector('#detail3TabsFrm');
                                            if (!iframe) return false;
                                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                            const input = iframeDoc.querySelector('#Product-lotNumber');
                                            return input && input.offsetParent !== null;
                                        })()
                                    ''')
                                    
                                    if input_exists:
                                        input_ready = True
                                        print("✅ Input field is ready!")
                                        break
                                except Exception as e:
                                    print(f"⚠️ Attempt {attempt + 1}: {e}")
                                
                                await asyncio.sleep(0.5)
                            
                            if not input_ready:
                                print("❌ Input field not found after waiting")
                                # Debug: ดูว่ามี input อะไรบ้าง
                                all_inputs = await imtpage2.evaluate('''
                                    (() => {
                                        const iframe = document.querySelector('#detail3TabsFrm');
                                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                        const inputs = iframeDoc.querySelectorAll('input');
                                        return Array.from(inputs).map(inp => ({
                                            id: inp.id,
                                            name: inp.name,
                                            type: inp.type,
                                            visible: inp.offsetParent !== null
                                        }));
                                    })()
                                ''')
                                print("🔍 All inputs found:", all_inputs)
                                continue  # ข้ามไปรายการถัดไป

                            await asyncio.sleep(0.5)
                            
                            for lotnumber in filtered_data:

                                if lotnumber["lot_number"] not in invoiceItemsStatus["product_items"] :

                                    print("📝 Entering Lot Number: ", lotnumber["lot_number"])
                                    await fill_input_in_iframe(imtpage2, 'Product-lotNumber', lotnumber["lot_number"])

                                    manufacturing_date_split = lotnumber["manufacturing_date"].split("-")          # ['2025', '05', '19']
                                    manufacturing_date = manufacturing_date_split[2] + manufacturing_date_split[1] + manufacturing_date_split[0]
                                    print("📝 Entering Manufacturing date: ", manufacturing_date)
                                    await fill_input_in_iframe(imtpage2, 'Product-manufacturingDate', manufacturing_date)

                                    expiration_date_split = lotnumber["expired_date"].split("-")          # ['2025', '05', '19']
                                    expiration_date = expiration_date_split[2] + expiration_date_split[1] + expiration_date_split[0]
                                    print("📝 Entering expiration date: ", expiration_date)
                                    await fill_input_in_iframe(imtpage2, 'Product-expireDate', expiration_date)

                                    # Find and fill measurement
                                    print("📝 Entering measurement: ", lotnumber["measurement"])
                                    await fill_input_in_iframe(imtpage2, 'Product-measurement', lotnumber["measurement"])

                                    # Find and fill measurementUnitCode
                                    print("📝 Entering measurementUnitCode: ", lotnumber["measurement_unit"])
                                    await fill_input_in_iframe(imtpage2, 'Product-measurementUnitCode', lotnumber["measurement_unit"])

                                    # Find and fill quantity
                                    print("📝 Entering quantity: ", lotnumber["qty"])
                                    await fill_input_in_iframe(imtpage2, 'Product-quantity', lotnumber["qty"])

                                    # Find and fill quantityUnitCode
                                    print("📝 Entering quantityUnitCode: ", "C62")
                                    await fill_input_in_iframe(imtpage2, 'Product-quantityUnitCode', "C62")

                                    # Find and click button Add Product-save
                                    print("🔘 button Product-save")
                                    try:
                                        print("🔘 Clicking Save button")
                                        await imtpage2.evaluate('''
                                            (() => {{
                                                const iframe = document.querySelector('#detail3TabsFrm');
                                                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                                                const saveButton = iframeDoc.querySelector('#Product-save');
                                                if (saveButton) {{
                                                    saveButton.click();
                                                    console.log('Button clicked');
                                                }}
                                            }})()
                                        ''')

                                        print("✅ Button Save clicked")
                                        update_input_data(input_data, invoice_number, item_code, 3, license_number, "process", lotnumber["lot_number"], len(detail["items"]), stepJob, reference_number, remark, remark_product)
                                        await take_screenshot(imtpage2, "step_lotNumber_" + invoice_number + "_" + item_code + "_" + lotnumber["lot_number"], reference_number)

                                        # await asyncio.sleep(3)
                                    except Exception as e:
                                        print(f"❌ Error clicking Product-save button: {e}")

            await imtpage2.close()
            print("✅ ปิด tab เรียบร้อยแล้ว")
    
    url_download = "https://imtl.nbgwhosting.com/imtl/IE5DEV.shippingnet/runtime/temp/"+reference_number+".pdf"

    download_and_upload_file(url_download, reference_number, "import_declaration")

    print("✅ Automation complete!")
    
    checkjobs = get_jobs_data_requests(reference_number)
    statusJob = checkjobs[0]["status"]

    checkStatusStep = checkjobs[0]["step"]

    statusStep1 = True

    if checkStatusStep["step1"] != "success":
        statusStep1 = False

    print("✅ Step 1: Success")

    # ตรวจสอบ step2
    all_complete = True

    if checkStatusStep["step2"] == []:
        all_complete = False
    else: 
        for invoice in checkStatusStep["step2"]:
            user_status = invoice["user_data_status"]
            if user_status != "success":
                all_complete = False
            for item in invoice["invoice_items"]:
                status = item["status"]
                if status != "success" or user_status != "success":
                    all_complete = False

    if statusStep1 and all_complete :
        statusJob = "Completed"
    else:
        statusJob = "Completed With Missing"

    payload = {
        "status": statusJob
    }

    update_step_job(reference_number, payload)
    # await asyncio.sleep(3)

    return statusJob

async def dialog_handler(event, page):
    print(f"🔍 จัดการตามประเภทของ dialog")

    if event.type_ == uc.cdp.page.DialogType.ALERT:
        # Alert - กด OK
        await page.send(uc.cdp.page.handle_java_script_dialog(accept=True))
        await asyncio.sleep(2)


        entrepreneur_click = await click_selector_with_retry(page, "ผู้ประกอบการ", max_retries=3, wait_time=2, button='left', click_count=2)
        # entrepreneur_click = await click_with_retry(page, "ผู้ประกอบการ", max_retries=3, wait_time=2)
        if not entrepreneur_click:
            print("❌ Failed to click ผู้ประกอบการ")

        await asyncio.sleep(1)

        digital_id_click = await click_selector_with_retry(page, "Digital ID", max_retries=3, wait_time=2, button='left', click_count=2)
        # digital_id_click = await click_with_retry(page, "Digital ID", max_retries=3, wait_time=2)
        if not digital_id_click:
            print("❌ Failed to click Digital ID")

        await asyncio.sleep(1)

        # Find customer name
        print("📝 Finding customer name after click dialog")
        # company_name = "บริษัท ซีเมนส์ เฮลท์แคร์ จำกัด"

        print(f"📝 Customer name: {GlobalState.company_name}")
        success_click_customer = await click_input_with_retry(
            page,
            f'input[type="submit"][value*="{GlobalState.company_name}"]',
            field_name=f"Customer: {GlobalState.company_name}",
            max_retries=3,
            wait_time=2,
            click_count=2
        )
        
        if not success_click_customer:
            print(f"❌ Cannot proceed - failed to click customer: {GlobalState.company_name}")
        
        await asyncio.sleep(1)

        print("📝 Finding License Per Invoice after click dialog")
        success_click_license_per_invoice = await click_input_with_retry(
            page,
            f'input[type="submit"][value="License per Invoice"]', 
            field_name=f"License Per Invoice",
            max_retries=3,
            wait_time=2,
            click_count=2
        )

        if not success_click_license_per_invoice:
            print(f"❌ Cannot proceed - failed to click License per Invoice")

        # await asyncio.sleep(5)

        if(page.url != "https://importlpi.fda.moph.go.th/SIP/Frm_ConvertCode.aspx"):
            print("📝 Finding Convert Code after click dialog")
            convert_code_click = await click_selector_with_retry(
                page, 
                f'a[href="Frm_ConvertCode.aspx"]',
                button='left',
                click_count=2
            )

            if not convert_code_click:
                print("❌ Cannot proceed - failed to click Convert Code")
                            

async def monitor_dialogs(page):
    page.add_handler(uc.cdp.page.JavascriptDialogOpening, dialog_handler)            

if __name__ == "__main__":
    uc.loop().run_until_complete(main())