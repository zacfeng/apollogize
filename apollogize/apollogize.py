'''
    Usage:
        python apollogize.py -u <user_name> -p <password> (-s <start_date>) (-e <end_date>)
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
    def __init__(self, username, password, sdt, edt, company_id, punches_location_id):
        self.__cookies = self.gen_cookies(username, password)
        self.__sdt = sdt
        self.__edt = edt
        self.__fails = list()
        self.__company_id = company_id
        self.__punches_location_id = punches_location_id

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
                'CompanyId': self.__company_id,
            },
        )
        return resp_pass.cookies

    def do_recheckin(self, att_type: int, dt: pendulum.datetime, hour: int):
        dt = dt.add(hours=hour)

        if att_type == 1:
            att = dt.add(minutes=randint(0, 30))
        else:
            att = dt.add(minutes=randint(31, 59))

        resp = requests.post(
            url='https://pt.mayohr.com/api/reCheckInApproval',
            cookies=self.__cookies,
            data={
                'AttendanceOn': att.to_datetime_string(),
                'AttendanceType': att_type,
                'IsBehalf': False,
                'PunchesLocationId': self.__punches_location_id,
            },
        )

        time.sleep(2)

        err = resp.json().get('Error', {}).get('Title')
        if resp.status_code == 200:
            LOGGER.info('%s att_type=%s success!', att.to_datetime_string(), att_type)
        elif resp.status_code == 400 and 'record of the day has existed' in err:
            LOGGER.info('%s: %s', att.to_datetime_string(), err)
        else:
            LOGGER.error('%s (code=%d, err=%s)', att.to_datetime_string(), resp.status_code, err)
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

            leave_start = pendulum.parse(leaves[0]['LeaveStartDatetime'])
            leave_end = pendulum.parse(leaves[0]['LeaveEndDatetime'])
            adjust_work_hour = set(range(2, 12)).difference(
                set(range(leave_start.hour, leave_end.hour + 1))
            )

            if adjust_work_hour:
                LOGGER.info(
                    'leave on %s, start=%s, end=%s', dobj, leave_start.time(), leave_end.time()
                )
                yield dobj, min(adjust_work_hour), max(adjust_work_hour)

    def process(self):
        for dt_month in pendulum.period(self.__sdt, self.__edt).range('months'):
            for d, shour, ehour in self.get_work_dates(dt_month):
                try:
                    self.do_recheckin(1, d, shour)  # recheckin work on
                    self.do_recheckin(2, d, ehour)  # recheckin work off
                except Exception as e:
                    LOGGER.error(e)
                    self.fails.append(d.to_date_string())
                else:
                    LOGGER.info('Apollogize successfully %s', d.to_date_string())


def entry():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '-u', required=True)
    parser.add_argument('--password', '-p', required=True)
    parser.add_argument('--sdt', '-s')
    parser.add_argument('--edt', '-e')
    parser.add_argument('--company_id', '-c')
    parser.add_argument('--punches_location_id', '-l')
    args = parser.parse_args()

    start = pendulum.parse(args.sdt) if args.sdt else pendulum.now().first_of('year')
    end = pendulum.parse(args.edt) if args.edt else pendulum.now()
    aplo = Apollogize(
        username=f'{args.username}@gogolook.com',
        password=args.password,
        sdt=start,
        edt=end,
        company_id=args.company_id,
        punches_location_id=args.punches_location_id,
    )

    aplo.process()

    if aplo.success:
        LOGGER.info('Success!')
    else:
        LOGGER.error('Please double check following data: %s', ', '.join(aplo.fails))
