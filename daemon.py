import os
import time
import zipfile
from datetime import datetime
from io import BytesIO

import requests
import json

import bambulabs_api as bl
import configparser
import redis
import json

from test import payload

def find_key_by_sn(dict_data, target_sn):
    for key, value in dict_data.items():
        if value.get('sn') == target_sn:
            return key
    return None  # Return None if no matching SN is found

def create_zip_archive_in_memory(
        text_content: str,
        text_file_name: str = 'file.txt') -> BytesIO:
    """
    Create a zip archive in memory

    Args:
        text_content (str): content of the text file
        text_file_name (str, optional): location of the text file.
            Defaults to 'file.txt'.

    Returns:
        io.BytesIO: zip archive in memory
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr(text_file_name, text_content)
    zip_buffer.seek(0)
    return zip_buffer

#dog doo hacks to get this thing up and running in a day
url = "http://127.0.0.1:8000/api/"

if __name__ == '__main__':
    Printers = {}
    r = redis.Redis(host='localhost', port=6379, db=0)

    config = configparser.ConfigParser()
    config.read('config.ini')
    for section in config.sections():
        Printers[section] = {}
        try:
            Printers[section]['sn'] = config.get(section, 'sn')
            Printers[section]['key'] = config.get(section, 'key')
            Printers[section]['ip'] = config.get(section, 'ip')
            try:
                Printers[section]['camera'] = config.getboolean(section, 'camera')
            except:
                Printers[section]['camera'] = True

        except Exception:
            print(f"REJECTING {section}")
            Printers.pop(section, None)
            continue

        Printers[section]['printer']:bl.Printer = bl.Printer(Printers[section]['ip'],Printers[section]['key'],Printers[section]['sn'])#,Printers[section]['camera'])

    for key in Printers:
        p:bl.Printer = Printers[key]['printer']
        p.connect()

    while True:
        time.sleep(2)
        #read all printers
        for key in Printers:

            p: bl.Printer = Printers[key]['printer']

            if not p.get_ready():
                print("not yet")
                continue

            state = p.get_state()


            cstate = p.get_current_state()
            btemp = p.get_bed_temperature()
            ptemp = p.get_nozzle_temperature()
            pnoozle = p.get_nozzle_diameter()
            mnoozle = p.get_nozzle_type()
            tstamp = datetime.now()

            printer_config = {
                'name': Printers[key]['sn'],
                'ip': Printers[key]['ip'],
                'access_code': Printers[key]['key'],
                'nozzle_diameter': pnoozle,
                'nozzle_type': mnoozle,
                'serial_number': Printers[key]['sn'],
                'state': f"{state}",
                'current_state': f"{cstate}",
            }
            sp = json.dumps(printer_config)
            headers = {'Content-Type': 'application/json'}

            response = requests.get(url+f"printer/{printer_config['serial_number']}")
            rr = ""
            if response.status_code != 200:

                rr = requests.request("POST", url, headers=headers, data=sp)
                i = 0
            else:
                rt = json.loads(response.text)
                rt.pop('id')
                rt.pop('name')
                printer_config.pop('name')
                if set(printer_config.values()) == set(rt.values()):
                    print("Values are identical (ignoring order).")
                else:
                    print("Values are different.")
                    rr = requests.request("PUT", url+f"/printer/{printer_config['serial_number']}", headers=headers, data=payload)
            #r.set(f"{key}_cfgs", sp)
            i = 0
            printer_state = {
                'state': f"{state}",
                'cstate': f"{cstate}",
                'btemp': f"{btemp}",
                'ptemp': f"{ptemp}",
                'tstamp': f"{tstamp}",
            }
            sp = json.dumps(printer_state)
            #r.rpush(f"{key}_data", sp)
        #now we check for prints
        print("checking for prints")
        try:
            k = r.lpop('print').decode('utf-8')
        except Exception as e:
            continue
        printer = json.loads(k)
        target_sn = printer['serial_number']
        result = find_key_by_sn(Printers, target_sn)

        if result:
            print(f"The main key for SN {target_sn} is: {result}")
            target_printer: bl.Printer = Printers[result]['printer']
            with open(printer['filepath'], "r") as file:
                gcode = file.read()

            gcode_location = "Metadata/plate_1.gcode"
            filename = f"{printer['filename']}.3mf"
            io_file = create_zip_archive_in_memory(gcode, gcode_location)
            if file:
                result = target_printer.upload_file(io_file, filename)
                if "226" not in result:
                    print("Error Uploading File to Printer")

                else:
                    print("Done Uploading/Sending Start Print Command")
                    target_printer.start_print(filename, 1)
                    print("Start Print Command Sent")
        else:
            print(f"No key found for SN {target_sn}")
        pass
    #read all printers and make a dict of them
