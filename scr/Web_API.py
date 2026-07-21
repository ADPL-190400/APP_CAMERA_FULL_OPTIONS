import cv2
import io
import requests
from datetime import datetime, timezone

user = None
pw = None
token = None
headers = {}


def get_url(direct):
    
    return f'https://aiot-api.m2m-sol.co.jp/api/v1/{direct}'



def get_api(user_name, password,remember=False):
    
    global token, headers, user , pw
    user = user_name
    pw = password
    data = {
          "email": user,
            "password": pw,
            # "remember": True
        }
    try:
        res = requests.post(get_url('auth/login'), data=data)



        res_json = res.json()

    except Exception as e:
        print("Lỗi kết nối API:", str(e))
        return False

    if res_json.get('success') is True:
        token = res_json['data']['token']
        headers = {
                "Authorization": f"Bearer {token}"
            }
        return True
    else:
        print('Login failed:')
        return False
    
    


def send_mobile_incident(frame_bgr,details,type_id,camera_id): # pp in working area without ppe 
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]  
    success, img_encoded = cv2.imencode('.jpg', frame_bgr, encode_param)
    if not success:
        print("Encode ảnh thất bại")
        return

    img_bytes = io.BytesIO(img_encoded.tobytes())
    
    file = {
            'image': ('employee.png', img_bytes, 'image/jpeg')
        }
    print("send incident to mobile")
    print("Type incident:", type_id,type(type_id))
    print("Camera ID:", camera_id, type(camera_id)) 
    

    incident_data = {
                        "status": "open",
                        "type_id": type_id,
                        "camera_id": camera_id,
                        "details": details,
                    }

        # post incident 
    try:
        res = requests.post(get_url('incident'),data=incident_data,files=file ,headers=headers , allow_redirects=False)
        print("Method gửi_incident_ppe:", res.request.method)
        print("URL gửi:", res.request.url)
        print("Status:", res.status_code)
        print("Response:", res.text)
    except Exception as e:
        print("Lỗi:", str(e))
        try:# sửa lại khi web ko trả về kq đung
            get_api(user,pw)
            res = requests.post(get_url('incident'),data=incident_data,files=file ,headers=headers , allow_redirects=False)
            print("Method gửi_send_mobile_incident:", res.request.method)
            print("URL gửi:", res.request.url)
            print("Status:", res.status_code)
            print("Response:", res.text)
        except:
            pass

        



def send_mobile_employee(frame_bgr,employee_id, camera_id,now):
    _, img_encoded = cv2.imencode('.png', frame_bgr)
    img_bytes = io.BytesIO(img_encoded.tobytes())
    file = {
            'image': ('employee.png', img_bytes, 'image/png')
        }
    
    now_utc = now.astimezone(timezone.utc)
    print('thoi gian:', now)
    check_time = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    print("check_time:", check_time)
        
    employee_data = {
            "camera_id":camera_id,

            "employee_id": employee_id,
            "check_time": check_time
        }
    
    
    

    # post incident 
    try:
        res = requests.post(get_url('employee-attendance'),data=employee_data,files=file ,headers=headers, allow_redirects=False)
        print("Method gửi_attendance:", res.request.method)
        print("URL gửi:", res.request.url)
        print("Status:", res.status_code)
        print("Response:", res.text)
    except Exception as e:
        print("Lỗi:", str(e))
        
        try: # sửa lại khi web ko trả về kq đung
            get_api(user,pw)
            res = requests.post(get_url('employee-attendance'),data=employee_data,files=file ,headers=headers, allow_redirects=False)
            print("Method gửi_send_mobile_employee:", res.request.method)
            print("URL gửi:", res.request.url)
            print("Status:", res.status_code)
            print("Response:", res.text)
        except:
            pass


def post_employee(employee_data):
    try:
        res = requests.post(get_url('employee'),data=employee_data,headers=headers, allow_redirects=False)
        
        # print("Method gửi:", res.request.method)
        # print("URL gửi:", res.request.url)
        # print("Status:", res.status_code)
        # print("Response:", res.text)
    except Exception as e:
        print("Lỗi:", str(e))
        try: # sửa lại khi web ko trả về kq đung
            get_api(user,pw)
            res = requests.post(get_url('employee'),data=employee_data,headers=headers, allow_redirects=False)
            # print("Method gửi_post_employee:", res.request.method)
            # print("URL gửi:", res.request.url)
            # print("Status:", res.status_code)
            # print("Response:", res.text)
        except:
            pass


def get_employee():
   
    res = requests.get(get_url('employee'), headers=headers, allow_redirects=False).json()
    if res.get('success', False):
        return res
    

      
    get_api(user,pw)
    
    res = requests.get(get_url('employee'), headers=headers, allow_redirects=False).json()
    return res



def delete_employee(id):
    res = requests.delete(get_url(f'employee/{id}'),headers=headers, allow_redirects=False)
    
    print(res)
    print(res.text)




def get_camera():
    res = requests.get(get_url('camera'), headers=headers, allow_redirects=False).json()
    print(res["data"])

def get_camera_by_mac(mac):
    # res = requests.get(get_url(f'camera?mac={mac}'), headers=headers, allow_redirects=False).json()
    # print(res)
    # if res.get('success', False):
    #     return res['data']
    return None

def add_camera(data_camera):
    

    res = requests.post(get_url('camera'),json=data_camera,headers=headers, allow_redirects=False)

