'''
    Usage:
        python3.7 apollogize.py <user_name> <password> (<on_broad_data>)
'''
import sys
import time
from datetime import datetime
from random import randint

import requests
from dateutil.relativedelta import relativedelta

company_id = 'bb04f185-9731-4348-a0e0-6834fe5dff58'

def gen_cookies(username, password) -> requests.cookies.RequestsCookieJar:
    resp_token = requests.post(url='https://auth.mayohr.com/Token', data={
        'username': username,
        'password': password,
        'grant_type': 'password',
    })

    print(resp_token)

    payload_auth = {
        'code': resp_token.json()['code'],
        'CompanyId': company_id,
    }
    resp_pass = requests.get(url='https://authcommon.mayohr.com/api/auth/checkticket', params=payload_auth)
    return resp_pass.cookies


def auto_failure_check(
    cookies: requests.cookies.RequestsCookieJar,
    work_date: str,
    start_hour: int = 2,
    end_hour: int = 11,
) -> str:
    url = 'https://pt.mayohr.com/api/reCheckInApproval'
    payload_in = {
        'AttendanceOn': f'{work_date}T{start_hour:02d}:{randint(0, 30):02d}:00+00:00',
        'AttendanceType': 1,
        'PunchesLocationId': 'e506b866-49f3-4c47-a324-cd8c4fa7b580',
        'IsBehalf': False,
    }
    resp_in = requests.post(url=url, cookies=cookies, data=payload_in)
    err_in = resp_in.json().get('Error', {}).get('Title', None)
    print(
        f'check in {payload_in['AttendanceOn']} '
        f'(code={resp_in.status_code}, err={err_in})'
    )
    time.sleep(2)

    payload_out = {
        'AttendanceOn': f'{work_date}T{end_hour:02d}:{randint(0, 59):02d}:00+00:00',
        'AttendanceType': 2,
        'PunchesLocationId': 'e506b866-49f3-4c47-a324-cd8c4fa7b580',
        'IsBehalf': False,
    }
    resp_out = requests.post(url=url, cookies=cookies, data=payload_out)
    err_out = resp_out.json().get('Error', {}).get('Title', None)
    print(
        f'check out {payload_out['AttendanceOn']} '
        f'(code={resp_out.status_code}, err={err_out})'
    )
    time.sleep(2)

    if err_out == 'Check out time cannot be earlier than check in time':
        return work_date


def main(username: str, password: str, cal: datetime.date):
    cookies = gen_cookies(username=username, password=password)
    url_cal = 'https://pt.mayohr.com/api/EmployeeCalendars/scheduling'
    payload_cal = {'year': cal.year, 'month': cal.month}
    resp = requests.get(url=url_cal, params=payload_cal, cookies=cookies)
    failed = []
    for day in resp.json()['Data']['Calendars']:
        # from pprint import pprint
        # pprint(day)
        # continue

        work_day = datetime.strptime(day['Date'][:10], '%Y-%m-%d')
        if work_day <= datetime.now() and day['ShiftSchedule']:
            is_on_duty = False if day['LeaveSheets'] else True
            is_work_day = day['ShiftSchedule']['WorkOnTime'] is not None
            is_on_board = work_day >= on_board
            result = None
            if is_work_day and is_on_duty and is_on_board:
                result = auto_failure_check(
                    cookies=cookies, work_date=str(work_day.date())
                )
            elif is_work_day and is_on_board and not is_on_duty:
                leave_start = datetime.fromisoformat(
                    day['LeaveSheets'][0]['LeaveStartDatetime']
                )
                leave_end = datetime.fromisoformat(
                    day['LeaveSheets'][0]['LeaveEndDatetime']
                )
                work_hours = set(range(2, 12))
                adjust_work_hour = work_hours.difference(
                    set(range(leave_start.hour, leave_end.hour + 1))
                )
                if len(adjust_work_hour) > 0:
                    result = auto_failure_check(
                        cookies=cookies,
                        work_date=str(work_day.date()),
                        start_hour=min(adjust_work_hour),
                        end_hour=max(adjust_work_hour),
                    )
                print(
                    f'{work_day.date()} requested a leave, '
                    f'leave_start={leave_start.time()}, leave_end={leave_end.time()}'
                )

            if result:
                failed.append(result)
    return failed


if __name__ == '__main__':
    on_board = datetime.strptime(
        f'{datetime.now().year}-01-02' if len(sys.argv) <= 3 else sys.argv[3],
        '%Y-%m-%d',
    )
    current_cal = datetime(datetime.now().year, 1, 1)
    err_date = []
    while current_cal <= datetime.now():
        err_date.extend(
            main(
                username=f'{sys.argv[1]}@gogolook.com',
                password=sys.argv[2],
                cal=current_cal.date(),
            )
        )
        current_cal += relativedelta(months=1)

    if err_date:
        print(
            f'{sys.argv[1]} please double check following data: {', '.join(err_date)}'
        )
    else:
        print('Done!')
