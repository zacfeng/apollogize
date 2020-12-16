'''
    Usage:
        python3.7 apollogize.py <user_name> <password> (<on_broad_data>)
'''
import argparse
import logging
import time
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

    def __init__(self, username, password, sdt, edt):
        self.__cookies = self.gen_cookies(username, password)
        self.__sdt = sdt
        self.__edt = edt
        self.__fails = list()

    @property
    def success(self):
        return not self.__fails

    @property
    def fails(self):
        return self.__fails

    def gen_cookies(self, username, password) -> requests.cookies.RequestsCookieJar:
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
            cookies=self.__cookies,
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
            LOGGER.info("%s att_type=%s success!", att_time, att_type)
        else:
            LOGGER.error("%s (code=%d, err=%s)", att_time, resp.status_code, err)
            raise Exception(err)

    def get_work_dates(self, dt: pendulum.datetime):
        resp = requests.get(
            url='https://pt.mayohr.com/api/EmployeeCalendars/scheduling',
            params={'year': dt.year, 'month': dt.month},
            cookies=self.__cookies,
        )
        for d in resp.json()['Data']['Calendars']:
            dobj = pendulum.parse(d['Date'])
            schedule = d.get('ShiftSchedule')
            leaves = d.get('LeaveSheets')

            valid = self.__sdt <= dobj <= pendulum.now() and schedule.get('WorkOnTime')

            if not valid:
                continue

            shour = 2  # 10 AM in Taipei time
            ehour = 11  # 7 PM in Taipei time

            if not leaves:
                yield dobj, shour, ehour
                continue

            print(leaves)

            leave_start = pendulum.parse(leaves[0]['LeaveStartDatetime'])
            leave_end = pendulum.parse(leaves[0]['LeaveEndDatetime'])
            adjust_work_hour = set(range(2, 12)).difference(
                set(range(leave_start.hour, leave_end.hour + 1))
            )

            if adjust_work_hour:
                LOGGER.info(
                    "leave on %s, start=%s, end=%s", dobj, leave_start.time(), leave_end.time()
                )
                yield dobj, min(adjust_work_hour), max(adjust_work_hour)

    def process(self):
        for dt_month in pendulum.period(self.__sdt, self.__edt).range('months'):
            for d, shour, ehour in self.get_work_dates(dt_month):
                try:
                    self.do_recheckin(1, d, shour)  # recheckin work on
                    self.do_recheckin(2, d, ehour)  # recheckin work off
                except Exception:
                    self.fails.append(d)
                else:
                    LOGGER.info('Apollogize successfully %s', d)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '-u', required=True)
    parser.add_argument('--password', '-p', required=True)
    parser.add_argument('--sdt', '-s')
    parser.add_argument('--edt', '-e')
    args = parser.parse_args()

    start = pendulum.parse(args.sdt) if args.sdt else pendulum.now().first_of('year')
    end = pendulum.parse(args.edt) if args.edt else pendulum.now()
    aplo = Apollogize(
        username=f'{args.username}@gogolook.com', password=args.password, sdt=start, edt=end
    )

    aplo.process()

    if aplo.success:
        LOGGER.info('Success!')
    else:
        LOGGER.error("Please double check following data: %s", ', '.join(aplo.fails))
