from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from ocr.forms import FileUploadForm, ReportDropdown, SubmitData, ServerDropdown
from pdf2image import convert_from_path
import os
import cv2
import pytesseract
from pytesseract import Output
import json
from ocr.dictionary import TAGS
from ocr.pi_config import AUTH, SERVER
import requests
import re
import datetime


UPLOAD_DIRECTORY = 'ocr\\uploads\\'

HEADERS = {"X-Requested-With": "XMLHttpRequest"}

ALLOWED_NUMBERS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "."]
ALLOWED_IN_TIMESTAMP = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "/"]
ALLOWED_IN_SERIAL_NO = ["A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
                        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "/"]
ALLOWED_IN_BOTTLED_ID = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ","]
ALLOWED_CHARS = ["A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
                 "a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r","s","t","u","v","w","x","y","z",
                 "0","1","2","3","4","5","6","7","8","9",
                 " "]


def upload(request):
    if request.method == 'POST':
        file_to_upload = FileUploadForm(request.POST, request.FILES)
        user_dd = ReportDropdown(request.POST)
        server_dd = ServerDropdown(request.POST)
        # GET selected value from DROPDOWN list
        selected_server = request.POST.get('server_site')
        selected_report = request.POST.get('report_type')
        print(f"selected_server_site: {selected_server}")
        print(f"selected_report: {selected_report}")

        if file_to_upload.is_valid():
            save_uploaded_file(request.FILES['file'])
            convert_to_image(request.FILES['file'].name)
            file = remove_file_extension(request.FILES['file'].name)
            # make a decision here which report to run
            if selected_report == 'sg':
                json_request = process_sg_folder(UPLOAD_DIRECTORY + file, selected_server)
                return render(request, "data-sg.html", json.loads(str(json.dumps({"data": json_request, "server": selected_server}))))
            elif selected_report == 'cs':
                json_request = process_cs_folder(UPLOAD_DIRECTORY + file, selected_server)
                return render(request, "data-cs.html", json.loads(str(json.dumps({"data": json_request, "server": selected_server}))))
            elif selected_report == 'tca':
                json_request = process_tca_folder(UPLOAD_DIRECTORY + file, selected_server)
                return render(request, "data-tca.html", json.loads(str(json.dumps({"data": json_request, "server": selected_server}))))
            elif selected_report == 'lubecheck':
                json_request = process_lubecheck_folder(UPLOAD_DIRECTORY + file, selected_server)
                return render(request, "data-lubecheck.html", json.loads(str(json.dumps({"data": json_request, "server": selected_server}))))

    else:   # show form
        file_to_upload = FileUploadForm()
        user_dd = ReportDropdown()
        server_dd = ServerDropdown()
        return render(request, "upload.html", {'upload_form': file_to_upload, 'dropdown_selection': user_dd, 'server_selection': server_dd})


def remove_file_extension(filename):
    filename = filename.split(".")[0]
    return filename


def save_uploaded_file(f):
    file = remove_file_extension(filename=f.name)
    if not os.path.isdir(UPLOAD_DIRECTORY + file+'/'):
        os.mkdir(UPLOAD_DIRECTORY + file+'/')
    with open(UPLOAD_DIRECTORY + f.name, 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)
    # convert_to_image(f.name)


def get_web_id(tag_name, server):
    print(f"GET WEB ID: SERVER: {server}")
    base_url = SERVER[server]['BASE_URL']
    data_server = SERVER[server]['DATA_SERVER']

    url = base_url + "/points?path=\\\\{}\\{}"
    url = url.format(data_server, tag_name)
    print(url)
    response = requests.get(url, auth=AUTH, timeout=20, headers=HEADERS, cert=False)
    return response.json()['WebId'], base_url


def upload_to_pi(timestamp, value, web_id, base_url):
    pi_data = {'Timestamp': timestamp,'Value': value}
    pi_data = json.dumps(pi_data)
    print(pi_data)
    url = base_url+"/streams/{}/value"
    url = url.format(web_id)
    print(url)
    response = requests.post(url, data=pi_data, auth=AUTH, verify=False, headers=HEADERS, cert=False)
    # print(response.status_code)

    return response.status_code


def crop_area_to_text(COORDINATES, image_to_process):
    x, y = COORDINATES[0], COORDINATES[1]
    w, h = COORDINATES[2] - x, COORDINATES[3] - y
    # crop using cv2
    img = cv2.imread(image_to_process)
    crop_img = img[y:y + h, x:x + w]

    crop_config = r"--psm 6 --oem 3"

    text = pytesseract.image_to_string(crop_img, config=crop_config, lang='eng')
    return text


def convert_to_image(filename):
    file = remove_file_extension(filename)
    pages = convert_from_path(UPLOAD_DIRECTORY + filename)
    print(pages)
    JPEG_FOLDER = UPLOAD_DIRECTORY+file+'\\'+filename

    # Saving pages in jpeg format by page
    for x, page in enumerate(pages):
        page.save(f'{JPEG_FOLDER}_page-{x}.jpg', 'JPEG')


def process_sg_folder(sg_directory, selected_server):
    print(f"SG directory: {sg_directory}")
    print(f"Selected Server: {selected_server}")
    files = os.listdir(sg_directory)

    # SG BOXES
    BOX_COORDINATES = {
        'value': [1180, 932, 1344, 1005],
        'location': [549, 603, 1450, 642],
        'report_date': [1259, 507, 1447, 552],
        'sample_date': [551, 670, 754, 704],
        'serial_no': [555, 639, 912, 674],
    }

    json_request = {}
    for idx, jpg in enumerate(files):  # all images within source folder
        try:
            jpg_path = sg_directory + '\\' + jpg
            value = crop_area_to_text(BOX_COORDINATES['value'], image_to_process=jpg_path)
            location = crop_area_to_text(BOX_COORDINATES['location'], image_to_process=jpg_path)
            report_date = crop_area_to_text(BOX_COORDINATES['report_date'], image_to_process=jpg_path)
            sample_date = crop_area_to_text(BOX_COORDINATES['sample_date'], image_to_process=jpg_path)
            serial_no = crop_area_to_text(BOX_COORDINATES['serial_no'], image_to_process=jpg_path)
            value, location, report_date, sample_date, serial_no = value.strip(), location.strip().replace(".",""), report_date.strip(), sample_date.strip(), serial_no.strip()
            print(f"value: {value}, location: {location}, report_date: {report_date}, sample_date: {sample_date}, serial_no: {serial_no}, server: {selected_server}")
            jpg_key = "jpg_" + str(idx)
            json_row = {"value":value,"location":location,"report_date":report_date, "sample_date": sample_date, "serial_no": serial_no, "site": selected_server}
            json_request[jpg_key] = json_row
        except Exception as e:
            print(f"File error: {e}")
    return json_request


def submit_sg_data(request):
    # FETCH data from on click of submit
    # print(request.GET)
    data_from_view = request.POST.get('data')
    server_from_view = request.POST.get('server')
    # print(data_from_view)
    print("After REDIRECT")
    if request.method == 'POST':
        print("After redirect and post")
        print("Clicked Submit button")
    # post to PI here
    json_request = upload_sg_data(data_from_view, server_from_view)
    return render(request, "uploaded-sg.html", json.loads(str(json.dumps({"data": json_request}))))
    # return HttpResponse('<p>Uploaded values to PI</p>')


def upload_sg_data(json_request, server):
    print(json_request)
    print(type(json_request))   # str
    json_request = json_request.replace("\'", "\"")
    json_request = json.loads(json_request)
    print("str to dict")
    print(json_request)
    print(type(json_request))

    status_codes_result = []

    for jpg in json_request:
        # print(json_request[jpg])
        location = json_request[jpg]['location']
        value = json_request[jpg]['value']
        report_date = json_request[jpg]['report_date']
        sample_date = json_request[jpg]['sample_date']
        serial_no = json_request[jpg]['serial_no']
        try:
            tag_name = TAGS['SG'][location]['value']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=value, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR, TAG NOT FOUND IN DICTIONARY")
    print(status_codes_result)
    return json_request


def process_cs_folder(sg_directory, selected_server):
    print(f"SG directory: {sg_directory}")
    print(f"Selected Server: {selected_server}")
    files = os.listdir(sg_directory)

    # CS BOXES
    BOX_COORDINATES = {
        'value': [1055, 916, 1474, 1167],
        'location': [551, 616, 1477, 652],
        'report_date': [1262, 510, 1475, 547],
        'sample_date': [555, 686, 722, 720],
        'serial_no': [552, 652, 722, 683],
    }
    json_request = {}
    for idx, jpg in enumerate(files):  # all images within source folder
        try:
            jpg_path = sg_directory + '\\' + jpg
            value = crop_area_to_text(BOX_COORDINATES['value'], image_to_process=jpg_path)
            location = crop_area_to_text(BOX_COORDINATES['location'], image_to_process=jpg_path)
            report_date = crop_area_to_text(BOX_COORDINATES['report_date'], image_to_process=jpg_path)
            sample_date = crop_area_to_text(BOX_COORDINATES['sample_date'], image_to_process=jpg_path)
            serial_no = crop_area_to_text(BOX_COORDINATES['serial_no'], image_to_process=jpg_path)
            value, location, report_date, sample_date, serial_no = value.strip(), location.strip().replace(".",""), report_date.strip(), sample_date.strip(), serial_no.strip()
            print(
                f"value: {value}, location: {location}, report_date: {report_date}, sample_date: {sample_date}, serial_no: {serial_no}, server: {selected_server}")
            jpg_key = "jpg_" + str(idx)
            json_row = {"value": value, "location": location, "report_date": report_date, "sample_date": sample_date,
                        "serial_no": serial_no, "site": selected_server}
            json_request[jpg_key] = json_row
        except Exception as e:
            print(f"File error: {e}")
    return json_request


def submit_cs_data(request):
    # FETCH data from on click of submit
    # print(request.GET)
    data_from_view = request.POST.get('data')
    server_from_view = request.POST.get('server')
    # print(data_from_view)
    print("After REDIRECT")
    if request.method == 'POST':
        print("After redirect and post")
        print("Clicked Submit button")
    # post to PI here
    upload_cs_data(data_from_view, server_from_view)
    json_request = upload_cs_data(data_from_view, server_from_view)
    return render(request, "uploaded-cs.html", json.loads(str(json.dumps({"data": json_request}))))


def upload_cs_data(json_request, server):
    print(json_request)
    print(type(json_request))   # str
    json_request = json_request.replace("\'", "\"")
    json_request = json.loads(json_request)
    print("str to dict")
    print(json_request)
    print(type(json_request))
    print(f"THE SERVER: {server}")

    for jpg in json_request:
        # print(json_request[jpg])
        location = json_request[jpg]['location']
        value = json_request[jpg]['value']
        report_date = json_request[jpg]['report_date']
        sample_date = json_request[jpg]['sample_date']
        serial_no = json_request[jpg]['serial_no']
        try:
            tag_name = TAGS['CS'][location]['value']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            upload_to_pi(timestamp=sample_date, value=value, web_id=web_id, base_url=base_url)
        except KeyError as e:
            print(f"Note: KEY ERROR, TAG NOT FOUND IN DICTIONARY")
    return json_request


def only_allowed_chars(this_string):
    for char in this_string:
        if char not in ALLOWED_CHARS:
            this_string = this_string.replace(char, "")
    return this_string


def only_allowed_in_timestamp(this_string):
    for char in this_string:
        if char not in ALLOWED_IN_TIMESTAMP:
            this_string = this_string.replace(char, "")
    return this_string


def only_allowed_in_serial_no(this_string):
    for char in this_string:
        if char not in ALLOWED_IN_SERIAL_NO:
            this_string = this_string.replace(char, "")
    return this_string


def only_allowed_in_numbers(this_string):
    for char in this_string:
        if char not in ALLOWED_NUMBERS:
            this_string = this_string.replace(char, "")
    return this_string

def only_allowed_in_bottled_id(this_string):
    for char in this_string:
        if char not in ALLOWED_IN_BOTTLED_ID:
            this_string = this_string.replace(char, "")
    return this_string


def process_tca_folder(tca_directory, selected_server):
    print(f"TCA directory: {tca_directory}")
    print(f"Selected Server: {selected_server}")
    files = os.listdir(tca_directory)

    # TCA BOXES
    BOX_COORDINATES = {
        'location': [870, 203, 1227, 241],
        'bank_and_phase': [867, 246, 1131, 274],
        'serial_no': [870, 281, 1045, 309],
        'report_date': [1387, 170, 1509, 205],
        'sample_date': [684, 459, 810, 493],
        'temperature': [759, 561, 798, 594],
        'hydrogen': [747, 614, 797, 641],
        'methane': [747, 647, 798, 674],
        'ethane': [747, 682, 797, 707],
        'ethylene': [751, 715, 801, 740],
        'acetylene': [751, 749, 801, 775],
    }

    json_request = {}
    for idx, jpg in enumerate(files):  # all images within source folder
        print(f"filename: {jpg}")
        jpg_num = jpg.split("-")[-1].replace(".jpg","")
        print(f"jpg_num: {jpg_num}")
        if int(jpg_num) % 3 == 0:
            try:
                jpg_path = tca_directory + '\\' + jpg
                location = crop_area_to_text(BOX_COORDINATES['location'], image_to_process=jpg_path)
                location = location.strip()
                location = only_allowed_chars(this_string=location)

                bank_and_phase = crop_area_to_text(BOX_COORDINATES['bank_and_phase'], image_to_process=jpg_path)
                bank_and_phase = bank_and_phase.strip()
                bank_and_phase = only_allowed_chars(this_string=bank_and_phase)

                serial_no = crop_area_to_text(BOX_COORDINATES['serial_no'], image_to_process=jpg_path)
                serial_no = serial_no.strip()
                serial_no = only_allowed_in_serial_no(this_string=serial_no)

                report_date = crop_area_to_text(BOX_COORDINATES['report_date'], image_to_process=jpg_path)
                report_date = report_date.strip()
                report_date = only_allowed_in_timestamp(this_string=report_date)

                sample_date = crop_area_to_text(BOX_COORDINATES['sample_date'], image_to_process=jpg_path)
                sample_date = sample_date.strip()
                sample_date = only_allowed_in_timestamp(this_string=sample_date)

                temperature = crop_area_to_text(BOX_COORDINATES['temperature'], image_to_process=jpg_path)
                temperature = temperature.strip()
                temperature = only_allowed_in_numbers(this_string=temperature)

                hydrogen = crop_area_to_text(BOX_COORDINATES['hydrogen'], image_to_process=jpg_path)
                print(f"hydrogen: {hydrogen}")
                hydrogen = hydrogen.strip()
                hydrogen = only_allowed_in_numbers(this_string=hydrogen)

                methane = crop_area_to_text(BOX_COORDINATES['methane'], image_to_process=jpg_path)
                methane = methane.strip()
                methane = only_allowed_in_numbers(this_string=methane)

                ethane = crop_area_to_text(BOX_COORDINATES['ethane'], image_to_process=jpg_path)
                ethane = ethane.strip()
                ethane = only_allowed_in_numbers(this_string=ethane)

                ethylene = crop_area_to_text(BOX_COORDINATES['ethylene'], image_to_process=jpg_path)
                ethylene = ethylene.strip()
                ethylene = only_allowed_in_numbers(this_string=ethylene)

                acetylene = crop_area_to_text(BOX_COORDINATES['acetylene'], image_to_process=jpg_path)
                acetylene = acetylene.strip()
                acetylene = only_allowed_in_numbers(this_string=acetylene)

                print(f"location: {location}, bank_and_phase: {bank_and_phase}, serial_no: {serial_no},"
                      f"report_date: {report_date}, sample_date: {sample_date},  temperature: {temperature}, "
                      f"hydrogen: {hydrogen}, methane: {methane}, ethane: {ethane},"
                      f"ethylene: {ethylene}, acetylene: {acetylene}, "
                      f"server: {selected_server}")
                jpg_key = "jpg_" + str(idx)
                json_row = {"location": location, "bank_and_phase": bank_and_phase, "serial_no": serial_no,
                            "report_date": report_date, "sample_date": sample_date, "temperature": temperature,
                            "hydrogen": hydrogen, "methane": methane, "ethane": ethane,
                            "ethylene": ethylene, "acetylene": acetylene,
                            "site": selected_server}
                json_request[jpg_key] = json_row
            except Exception as e:
                print(f"File error: {e}")
    return json_request


def upload_tca_data(json_request, server):
    print(json_request)
    print(type(json_request))   # str
    json_request = json_request.replace("\'", "\"")
    json_request = json.loads(json_request)
    print("str to dict")
    print(json_request)
    print(type(json_request))

    status_codes_result = []

    for jpg in json_request:
        # print(json_request[jpg])
        location = json_request[jpg]['location']
        bank_and_phase = json_request[jpg]['bank_and_phase']
        serial_no = json_request[jpg]['serial_no']
        report_date = json_request[jpg]['report_date']
        sample_date = json_request[jpg]['sample_date']
        temperature = json_request[jpg]['temperature']
        hydrogen = json_request[jpg]['hydrogen']
        methane = json_request[jpg]['methane']
        ethane = json_request[jpg]['ethane']
        ethylene = json_request[jpg]['ethylene']
        acetylene = json_request[jpg]['acetylene']

        key = location + " " + bank_and_phase
        key = re.sub(' +', ' ', key)        # remove multiple spaces in key

        # Uploading different data
        try:
            tag_name = TAGS['TCA'][key]['temperature']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=temperature, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['TCA'][key]['hydrogen']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=hydrogen, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['TCA'][key]['methane']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=methane, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['TCA'][key]['ethane']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=ethane, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['TCA'][key]['ethylene']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=ethylene, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['TCA'][key]['acetylene']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=sample_date, value=acetylene, web_id=web_id,
                                                 base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")

    print(status_codes_result)
    return json_request


def submit_tca_data(request):
    # FETCH data from on click of submit
    # print(request.GET)
    data_from_view = request.POST.get('data')
    server_from_view = request.POST.get('server')
    # print(data_from_view)
    print("After REDIRECT")
    if request.method == 'POST':
        print("After redirect and post")
        print("Clicked Submit button")
    # post to PI here
    json_request = upload_tca_data(data_from_view, server_from_view)
    return render(request, "uploaded-tca.html", json.loads(str(json.dumps({"data": json_request}))))
    # return HttpResponse('<p>Uploaded values to PI</p>')


def process_lubecheck_folder(lubecheck_directory, selected_server):
    print(f"Lubecheck directory: {lubecheck_directory}")
    print(f"Selected Server: {selected_server}")
    files = os.listdir(lubecheck_directory)

    # LUBECHECK BOXES
    BOX_COORDINATES = {
        'name': [243, 200, 676, 253],
        'name_site': [245, 320, 326, 348],
        'code': [246, 166, 440, 195],
        'unit_id': [839, 169, 997, 205],
        'unit_type': [839, 230, 934, 258],
        'lab_id': [524, 876, 655, 902],
        'bottled_id': [518, 905, 665, 929],
        'date_sampled': [530, 932, 654, 953],
        'oil_hours': [546, 956, 633, 978],
        'unit_hours': [546, 981, 624, 1002],
        'oil_change': [519, 1005, 636, 1024],
        'Wear_viscosity_at_40': [486, 1440, 543, 1462],
        'Wear_TAN': [486, 1538, 543, 1560],
    }

    json_request = {}
    for idx, jpg in enumerate(files):  # all images within source folder
        print(f"filename: {jpg}")
        jpg_num = jpg.split("-")[-1].replace(".jpg","")
        print(f"jpg_num: {jpg_num}")
        if jpg_num == '0':  # for page 1 of Lubecheck report
            try:
                jpg_path = lubecheck_directory + '\\' + jpg
                name = crop_area_to_text(BOX_COORDINATES['name'], image_to_process=jpg_path)
                name = name.strip()
                name = only_allowed_chars(this_string=name)

                name_site = crop_area_to_text(BOX_COORDINATES['name_site'], image_to_process=jpg_path)
                name_site = name_site.strip()
                name_site = only_allowed_chars(this_string=name_site)

                code = crop_area_to_text(BOX_COORDINATES['code'], image_to_process=jpg_path)
                code = code.strip()
                code = only_allowed_chars(this_string=code)

                unit_id = crop_area_to_text(BOX_COORDINATES['unit_id'], image_to_process=jpg_path)
                unit_id = unit_id.strip()
                unit_id = only_allowed_chars(this_string=unit_id)

                unit_type = crop_area_to_text(BOX_COORDINATES['unit_type'], image_to_process=jpg_path)
                unit_type = unit_type.strip()
                unit_type = only_allowed_chars(this_string=unit_type)

                lab_id = crop_area_to_text(BOX_COORDINATES['lab_id'], image_to_process=jpg_path)
                lab_id = lab_id.strip()
                lab_id = only_allowed_in_numbers(this_string=lab_id)

                bottled_id = crop_area_to_text(BOX_COORDINATES['bottled_id'], image_to_process=jpg_path)
                bottled_id = bottled_id.strip()
                bottled_id = only_allowed_in_bottled_id(this_string=bottled_id)

                date_sampled = crop_area_to_text(BOX_COORDINATES['date_sampled'], image_to_process=jpg_path)
                date_sampled = date_sampled.strip()
                # NOTE: Convert to appropriate format from 13-Sep-19
                # date_sampled = only_allowed_in_timestamp(this_string=date_sampled)

                oil_hours = crop_area_to_text(BOX_COORDINATES['oil_hours'], image_to_process=jpg_path)
                oil_hours = oil_hours.strip()
                oil_hours = only_allowed_in_numbers(this_string=oil_hours)

                unit_hours = crop_area_to_text(BOX_COORDINATES['unit_hours'], image_to_process=jpg_path)
                unit_hours = unit_hours.strip()
                unit_hours = only_allowed_in_numbers(this_string=unit_hours)

                oil_change = crop_area_to_text(BOX_COORDINATES['oil_change'], image_to_process=jpg_path)
                oil_change = oil_change.strip()
                oil_change = only_allowed_in_timestamp(this_string=oil_change)

                Wear_viscosity_at_40 = crop_area_to_text(BOX_COORDINATES['Wear_viscosity_at_40'], image_to_process=jpg_path)
                Wear_viscosity_at_40 = Wear_viscosity_at_40.strip()
                Wear_viscosity_at_40 = only_allowed_in_numbers(this_string=Wear_viscosity_at_40)

                Wear_TAN = crop_area_to_text(BOX_COORDINATES['Wear_TAN'], image_to_process=jpg_path)
                Wear_TAN = Wear_TAN.strip()
                Wear_TAN = only_allowed_in_numbers(this_string=Wear_TAN)

                print(f"name: {name}, name_site: {name_site}, code: {code}, unit_id: {unit_id}, unit_type: {unit_type}, lab_id: {lab_id}, "
                      f"bottled_id: {bottled_id}, date_sampled: {date_sampled},  oil_hours: {oil_hours}, unit_hours: {unit_hours},"
                      f"oil_change: {oil_change}, Wear_viscosity_at_40: {Wear_viscosity_at_40}, Wear_TAN: {Wear_TAN}")
                jpg_key = "jpg_" + str(idx)
                json_row = {"name": name, "name_site": name_site, "code": code, "unit_id": unit_id, "unit_type": unit_type, "lab_id": lab_id,
                            "bottled_id": bottled_id, "date_sampled": date_sampled, "oil_hours": oil_hours, "unit_hours": unit_hours,
                            "oil_change": oil_change, "Wear_viscosity_at_40": Wear_viscosity_at_40, "Wear_TAN": Wear_TAN,
                            "site": selected_server}
                json_request[jpg_key] = json_row
            except Exception as e:
                print(f"File error: {e}")
    return json_request


def submit_lubecheck_data(request):
    # FETCH data from on click of submit
    # print(request.GET)
    data_from_view = request.POST.get('data')
    server_from_view = request.POST.get('server')
    # print(data_from_view)
    print("After REDIRECT")
    if request.method == 'POST':
        print("After redirect and post")
        print("Clicked Submit button")
    # post to PI here
    json_request = upload_lubecheck_data(data_from_view, server_from_view)
    return render(request, "uploaded-lubecheck.html", json.loads(str(json.dumps({"data": json_request}))))
    # return HttpResponse('<p>Uploaded values to PI</p>')


def covert_date_1(date_time_string):
    # date_time_str = '2018-06-29 08:15:27.243860'
    date_time_obj = datetime.datetime.strptime(date_time_string, '%d-%b-%y')
    formatted_date_time = date_time_obj.strftime("%m/%d/%Y 00:00:00")
    return formatted_date_time


def upload_lubecheck_data(json_request, server):
    print(json_request)
    print(type(json_request))   # str
    json_request = json_request.replace("\'", "\"")
    json_request = json.loads(json_request)
    print("str to dict")
    print(json_request)
    print(type(json_request))

    status_codes_result = []

    for jpg in json_request:
        # print(json_request[jpg])
        name = json_request[jpg]['name']
        name_site = json_request[jpg]['name_site']
        code = json_request[jpg]['code']
        unit_id = json_request[jpg]['unit_id']
        unit_type = json_request[jpg]['unit_type']
        lab_id = json_request[jpg]['lab_id']
        bottled_id = json_request[jpg]['bottled_id']
        date_sampled = json_request[jpg]['date_sampled']        # timestamp ?   Convert first before uploading
        oil_hours = json_request[jpg]['oil_hours']
        unit_hours = json_request[jpg]['unit_hours']
        oil_change = json_request[jpg]['oil_change']
        Wear_viscosity_at_40 = json_request[jpg]['Wear_viscosity_at_40']
        Wear_TAN = json_request[jpg]['Wear_TAN']

        key = name + " " + name_site     # specify unique dictionary key here
        key = re.sub(' +', ' ', key)        # remove multiple spaces in key

        # Convert time
        date_sampled = covert_date_1(date_time_string=date_sampled)
        print(f"FORMATTED DATE: {date_sampled}")
        # Uploading different data
        try:
            tag_name = TAGS['LUBECHECK'][key]['oil_hours']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=date_sampled, value=oil_hours, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['LUBECHECK'][key]['unit_hours']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=date_sampled, value=unit_hours, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['LUBECHECK'][key]['oil_change']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=date_sampled, value=oil_change, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['LUBECHECK'][key]['Wear_viscosity_at_40']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=date_sampled, value=Wear_viscosity_at_40, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")
        try:
            tag_name = TAGS['LUBECHECK'][key]['Wear_TAN']
            web_id, base_url = get_web_id(tag_name=tag_name, server=server)
            status_code = upload_to_pi(timestamp=date_sampled, value=Wear_TAN, web_id=web_id, base_url=base_url)
            status_codes_result.append(status_code)
        except KeyError as e:
            print(f"Note: KEY ERROR {e}, TAG NOT FOUND IN DICTIONARY")

    print(status_codes_result)
    return json_request


