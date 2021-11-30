import logging
import time
from random import randint
from typing import List

import pendulum
import requests
from prompt_toolkit import print_formatted_text, prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.validation import Validator
from apollogize.version import __version__

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
)

LOGGER = logging.getLogger(__file__)
print = print_formatted_text


class RecheckinError(Exception):
    pass


class Apollogize:
    def __init__(
        self,
        username: str,
        password: str,
        sdt: pendulum.Date,
        edt: pendulum.Date,
        company_id: str,
        punches_location_id: str,
    ):
        self.__username = username
        self.__password = password
        self.__sdt = sdt
        self.__edt = edt
        self.__company_id = company_id
        self.__punches_location_id = punches_location_id
        self.__cookie = None

    def gen_cookies(self) -> requests.cookies.RequestsCookieJar:
        resp = requests.post(
            url='https://auth.mayohr.com/Token',
            data={
                'username': self.__username,
                'password': self.__password,
                'grant_type': 'password',
            },
        )

        if resp.status_code != 200:
            print(resp.json())
            exit(2)

        resp_pass = requests.get(
            url='https://authcommon.mayohr.com/api/auth/checkticket',
            params={
                'code': resp.json()['code'],
                'CompanyId': self.__company_id,
            },
        )
        return resp_pass.cookies

    def get_work_dates(self, dt: pendulum.datetime):
        resp = requests.get(
            url='https://pt.mayohr.com/api/EmployeeCalendars/scheduling',
            params={'year': dt.year, 'month': dt.month},
            cookies=self.__cookie,
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

    def all_dates(self):
        for dt_month in pendulum.period(self.__sdt, self.__edt).range('months'):
            for d, shour, ehour in self.get_work_dates(dt_month):
                if self.__sdt <= d <= self.__edt:
                    yield (d, shour, ehour)

    def do_recheckin(self, att_type: int, dt: pendulum.datetime, hour: int):
        dt = dt.add(hours=hour)

        if att_type == 1:
            att = dt.add(minutes=randint(0, 30))
        else:
            att = dt.add(minutes=randint(31, 59))

        resp = requests.post(
            url='https://pt.mayohr.com/api/reCheckInApproval',
            cookies=self.__cookie,
            data={
                'AttendanceOn': att.to_datetime_string(),
                'AttendanceType': att_type,
                'IsBehalf': False,
                'PunchesLocationId': self.__punches_location_id,
            },
        )

        time.sleep(1)

        err = resp.json().get('Error', {}).get('Title')
        if resp.status_code == 200:
            LOGGER.info('%s att_type=%s success!', att.add(hours=8).to_datetime_string(), att_type)
        elif resp.status_code == 400 and 'record of the day has existed' in err:
            LOGGER.info('%s: %s', att.to_datetime_string(), err)
        else:
            LOGGER.error('%s (code=%d, err=%s)', att.add(hours=8).to_datetime_string(), resp.status_code, err)
            raise RecheckinError(
                {'dt': att.to_datetime_string(), 'type': att_type, 'code': resp.status_code, 'err': err}
            )

    def process(self) -> List[str]:
        fails = list()
        self.__cookie = self.gen_cookies()

        print(FormattedText([('ansiyellow', 'Start submitting..')]))
        for d, shour, ehour in self.all_dates():
            try:
                self.do_recheckin(1, d, shour)  # recheckin work on
                self.do_recheckin(2, d, ehour)  # recheckin work off
            except RecheckinError as e:
                details = e.args[0]
                fails.append((details['dt'], details['type'], details['code'], details['err']))

        return fails


def is_valid_username(username) -> bool:
    import re

    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if re.fullmatch(regex, username):
        return True
    else:
        return False


username_validator = Validator.from_callable(
    is_valid_username,
    error_message='Not a valid username (should be your email).',
    move_cursor_to_end=True,
)


def entry():
    welcome_str = FormattedText(
        [
            (
                'ansigreen',
                '==================================================== \n  '
                f'Welcome to Apollogize-v{__version__} (Now is {pendulum.now().to_date_string()}) \n'
                '====================================================',
            ),
        ]
    )
    print(welcome_str)

    username_prompt = FormattedText([('ansiyellow', '1. Username(user@google.com): ')])
    username = prompt(username_prompt, validator=username_validator, validate_while_typing=True)

    password_prompt = FormattedText([('ansiyellow', '2. Password: ')])
    password = prompt(password_prompt, is_password=True)

    start_of_year = pendulum.now().first_of('year').to_date_string()
    start_of_month = pendulum.now().first_of('month').to_date_string()
    today = pendulum.now().to_date_string()
    end_of_year = pendulum.now().end_of('year').to_date_string()

    sdt_prompt = FormattedText(
        [('ansiyellow', '3. Start date(leave onboard day if you are new this year): ')]
    )
    sdt_completer = WordCompleter([start_of_year, start_of_month, today])
    sdt = prompt(sdt_prompt, completer=sdt_completer)

    edt_prompt = FormattedText([('ansiyellow', '4. End date: ')])
    edt_completer = WordCompleter([today, end_of_year])
    edt = prompt(edt_prompt, completer=edt_completer)

    company_id_prompt = FormattedText([('ansiyellow', '5. Your company id: ')])
    company_id = prompt(company_id_prompt)

    punches_location_id_prompt = FormattedText([('ansiyellow', '6. Your punches location id: ')])
    punches_location_id = prompt(punches_location_id_prompt)

    aplo = Apollogize(username, password, pendulum.parse(sdt), pendulum.parse(edt), company_id, punches_location_id)
    fails = aplo.process()

    if fails:
        print(FormattedText([('ansiyellow', 'Please check following data: ')]))
        for fail in fails:
            print(FormattedText([('ansired', f'{fail[0]} {fail[1]} {fail[2]} {fail[3]}')]))


if __name__ == '__main__':
    entry()
