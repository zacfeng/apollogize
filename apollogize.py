'''
    Usage:
        python3.7 apollogize.py <user_name> <password> (<on_broad_data>)
'''
import argparse
import logging
import time
from datetime import datetime
from random import randint

import pendulum
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
)

LOGGER = logging.getLogger(__file__)


class Apollogize:

    COMPANY_ID = 'bb04f185-9731-4348-a0e0-6834fe5dff58'
    PUNCHES_LOCATION_ID = 'e506b866-49f3-4c47-a324-cd8c4fa7b580'

    def __init__(self, username, password, starting_dt):
        self.cookies = self.gen_cookies(username, password)
        self.starting_dt = starting_dt
        self.fail_dts = list()

    @property
    def success(self):
        return not self.fail_dts

    @property
    def fail_dts(self):
        return self.fail_dts

    def gen_cookies(
        self, username, password
    ) -> requests.cookies.RequestsCookieJar:
        resp_token = requests.post(
            url='https://auth.mayohr.com/Token',
            data={
                'username': username,
                'password': password,
                'grant_type': 'password',
            },
        )

        if resp_token.status_code != 200:
            LOGGER.error('Wrong username or password!')
            exit(1)

        resp_pass = requests.get(
            url='https://authcommon.mayohr.com/api/auth/checkticket',
            params={
                'code': resp_token.json()['code'],
                'CompanyId': self.COMPANY_ID,
            },
        )
        return resp_pass.cookies

    def do_recheckin(self, att_type: int, work_dt: str, hour: str):
        att_time = f'{work_dt}T{hour:02d}:{randint(0, 30):02d}:00+00:00'
        resp = requests.post(
            url='https://pt.mayohr.com/api/reCheckInApproval',
            cookies=self.cookies,
            data={
                'AttendanceOn': att_time,
                'AttendanceType': att_type,
                'PunchesLocationId': self.PUNCHES_LOCATION_ID,
                'IsBehalf': False,
            },
        )

        time.sleep(2)
        err = resp.json().get('Error', {}).get('Title')
        if resp.status_code == 200:
            LOGGER.INFO(f'{att_time} att_type={att_type} success!')
        else:
            LOGGER.ERROR(f'{att_time} (code={resp.status_code}, err={err})')
            raise Exception(err)

    def get_work_dates(self, dt: pendulum.datetime.DateTime):
        resp = requests.get(
            url='https://pt.mayohr.com/api/EmployeeCalendars/scheduling',
            params={'year': dt.year, 'month': dt.month},
            cookies=self.cookies,
        )
        for dt_cal in resp.json()['Data']['Calendars']:
            work_dt = datetime.strptime(dt_cal['Date'][:10], '%Y-%m-%d')
            is_valid_dt = work_dt <= datetime.now() and dt['ShiftSchedule']
            exist_leave = False if dt_cal['LeaveSheets'] else True
            is_work_day = dt_cal['ShiftSchedule']['WorkOnTime'] is not None
            is_in_range = dt_cal >= self.starting_dt

            if is_valid_dt and is_work_day and is_in_range:
                s_hour = 2  # 10 AM in Taipei time
                e_hour = 11  # 7 PM in Taipei time
                if exist_leave:
                    leave_start = pendulum.parse(dt_cal['LeaveSheets'][0]['LeaveStartDatetime'])
                    leave_end = pendulum.parse(dt_cal['LeaveSheets'][0]['LeaveEndDatetime'])
                    adjust_work_hour = set(range(2, 12)).difference(
                        set(range(leave_start.hour, leave_end.hour + 1))
                    )
                    if adjust_work_hour:
                        LOGGER.INFO(
                            f'leave on {work_dt}, start={leave_start.time()}, end={leave_end.time()}'
                        )
                        yield dt_cal, min(adjust_work_hour), max(adjust_work_hour)

                yield dt_cal, s_hour, e_hour

    def process(self, dt: pendulum.datetime.DateTime):
        for dt, s_hour, e_hour in self.get_work_dates(dt):
            try:
                self.do_recheckin(1, dt, s_hour)  # recheckin work on
                self.do_recheckin(2, dt, e_hour)  # recheckin work off
            except:
                self.fail_dts.append(dt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '-u', required=True)
    parser.add_argument('--password', '-p', required=True)
    parser.add_argument('--starting_dt', '-s')
    args = parser.parse_args()

    start = pendulum.now().first_of('year')
    end = pendulum.now()
    aplo = Apollogize(
        username=f'{args.username}@gogolook.com',
        password=args.password,
        starting_dt=pendulum.parse(args.starting_dt) if args.starting_dt else start.to_date_string(),
    )

    for dt_month in pendulum.period(start, end).range('months'):
        aplo.process(dt_month)

    # if aplo.success:
    #     LOGGER.INFO('Success!')
    # else:
    #     LOGGER.ERROR(
    #         f"Please double check following data: {', '.join(aplo.fail_dts)}"
    #     )
