import json
import os
import re

import requests
from bs4 import BeautifulSoup

def get_building_and_apartment_number(name: str) -> tuple[str, str]:
    m = re.match(r'[Ő|Ö]rmező\s?(\w)\D*(\d*)', name)

    if m is None:
        return ("-", "-")

    g = m.groups()

    return (g[0], g[1])


def get_prometheus_text(data: list[dict]) -> str:
    lines = []

    lines.append("# HELP water_temperature Water temperature")
    lines.append("# TYPE water_temperature gauge")
    for item in data:
        water_temperature = item['ICON']['WTEMP']
        name = item['ICON']['NAME']
        building_and_apartment_number = get_building_and_apartment_number(name)
        if water_temperature != '-':
            lines.append(f'water_temperature{{name="{name}",building="{building_and_apartment_number[0]}",apartment_number="{building_and_apartment_number[1]}"}} {water_temperature}')

    lines.append("# HELP external_temperature External temperature")
    lines.append("# TYPE external_temperature gauge")
    for item in data:
        external_temperature = item['ICON']['ETEMP']
        name = item['ICON']['NAME']
        building_and_apartment_number = get_building_and_apartment_number(name)
        if external_temperature != '-':
            lines.append(f'external_temperature{{name="{name}",building="{building_and_apartment_number[0]}",apartment_number="{building_and_apartment_number[1]}"}} {external_temperature}')

    lines.append("# HELP current_room_temperature Current room temperature")
    lines.append("# TYPE current_room_temperature gauge")
    for item in data:
        name = item['ICON']['NAME']
        building_and_apartment_number = get_building_and_apartment_number(name)
        for room in item['ICON']['DP']:
            room_name = room['title']
            current_room_temperature = room['TEMP']
            pump_sate = 'active' if room['OUT']  == 1 else 'idle'
            lines.append(f'current_room_temperature{{name="{name}",building="{building_and_apartment_number[0]}",apartment_number="{building_and_apartment_number[1]}",room="{room_name}",pump_state="{pump_sate}"}} {current_room_temperature}')

    lines.append("# HELP target_room_temperature Target room temperature")
    lines.append("# TYPE target_room_temperature gauge")
    for item in data:
        name = item['ICON']['NAME']
        building_and_apartment_number = get_building_and_apartment_number(name)
        for room in item['ICON']['DP']:
            room_name = room['title']
            target_room_temperature = room['REQ']
            pump_sate = 'active' if room['OUT']  == 1 else 'idle'
            lines.append(f'target_room_temperature{{name="{name}",building="{building_and_apartment_number[0]}",apartment_number="{building_and_apartment_number[1]}",room="{room_name}",pump_state="{pump_sate}"}} {target_room_temperature}')

    lines.append("# HELP pump_state Pump state")
    lines.append("# TYPE pump_state gauge")
    for item in data:
        name = item['ICON']['NAME']
        building_and_apartment_number = get_building_and_apartment_number(name)
        for room in item['ICON']['DP']:
            room_name = room['title']
            pump_sate = room['OUT']
            lines.append(f'pump_state{{name="{name}",building="{building_and_apartment_number[0]}",apartment_number="{building_and_apartment_number[1]}",room="{room_name}"}} {pump_sate}')

    lines.append("# HELP overheat_state Overheat state")
    lines.append("# TYPE overheat_state gauge")
    for item in data:
        name = item['ICON']['NAME']
        building_and_apartment_number = get_building_and_apartment_number(name)
        overheat_state = 0 if item['ICON']['OVERHEAT'] == 'inaktív' else 1
        lines.append(f'overheat_state{{name="{name}",building="{building_and_apartment_number[0]}",apartment_number="{building_and_apartment_number[1]}"}} {overheat_state}')

    return '\n'.join(lines)


def get_csrf_token(login_page: requests.Response) -> str:
    login_page_soup = BeautifulSoup(login_page.text, 'html.parser')

    token = login_page_soup.select('input[type="hidden"][name="token"]')
    token_value = token[0]['value']

    return token_value


def get_phpsessid(login_page: requests.Response) -> str:
    return login_page.cookies['PHPSESSID']


def login() -> dict:
    login_page = requests.get('https://www.enzoldhazam.hu/')

    csrf_token_value = get_csrf_token(login_page)
    phpsessid_value = get_phpsessid(login_page)

    cookie_PHPSESSID = {'PHPSESSID': phpsessid_value}

    requests.post(
        'https://www.enzoldhazam.hu/', 
        data = {
            'username': os.environ.get('NGBS_USERNAME'),
            'password': os.environ.get('NGBS_PASSWORD'),
            'x-email': '',
            'token': csrf_token_value
        }, 
        cookies = cookie_PHPSESSID)

    return cookie_PHPSESSID


def get_device_data_from_ngbs(snr: str, session_cookie: dict) -> dict:
    data = requests.get(f'https://www.enzoldhazam.hu/Ax?action=iconByID&serial={snr}', cookies = session_cookie)

    return json.loads(data.text)

def get_devices(session_cookie: dict) -> dict:
    response = requests.get(f'https://www.enzoldhazam.hu/Ax?action=iconList', cookies = session_cookie)

    return json.loads(response.text)


def get_data() -> dict:
    session_cookie = login()

    get_devices_response = get_devices(session_cookie)

    data = []
    for snr in get_devices_response['ICONS']:
        data.append(get_device_data_from_ngbs(snr, session_cookie))

    return data


def lambda_handler(event, context) -> dict:
    data = get_data()

    prom_text = get_prometheus_text(data)

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": { "Content-Type": "text/plain; charset=utf-8" },
        "body": prom_text
    }


if __name__ == "__main__":
    res = lambda_handler(None, None)
    print(res['body'])