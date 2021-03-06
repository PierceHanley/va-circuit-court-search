import cookielib
import os
import re
import sys
import urllib
import urllib2
from bs4 import BeautifulSoup
from time import sleep

user_agent = u"Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.6; en-US; " + \
    u"rv:1.9.2.11) Gecko/20101012 Firefox/3.6.11"

courts_with_fm_case_number = {
    'Charlotte Circuit Court': '5',
    'Chesterfield Circuit Court': '5',
    'Goochland Circuit Court': '0',
    'Lee Circuit Court': '4',
    'Page Circuit Court': '5',
    'Richmond City Circuit Court': '5',
    'Wise Circuit Court': '5'
}

courts_with_continuing_case_numbers = {
    'Amherst Circuit Court': [(14890, 15204)],
    'Bedford Circuit Court': [(11169, 11554)],
    'Bristol Circuit Court': [(1018, 1483)],
    'Clarke Circuit Court': [(7390, 7675)],
    'Franklin Circuit Court': [(19481, 19850), (56075, 56757)],
    'Loudoun Circuit Court': [(26174, 27371)],
    'Madison Circuit Court': [(5577, 5705)],
    'Radford Circuit Court': [(12707, 13605)],
    'Russell Circuit Court': [(2681, 2768), (15845, 15999), (16959, 17891)],
    'Williamsburg/James City County Circuit Court': [(23238, 24221)],
    'York County/Poquoson Circuit Court': [(8011, 8446)]
}

courts_without_year_in_prefix = [
    'Loudoun Circuit Court'
]

def get_case_number(court, case_count, charge_count):
    case_numbers = []
    
    prefix = 'CR14'
    if court in courts_without_year_in_prefix:
        prefix = 'CR00'
    
    case = format(case_count, '06')
    if court in courts_with_continuing_case_numbers:
        case = format(0, '06')
        case_number_spans = courts_with_continuing_case_numbers[court]
        for span in case_number_spans:
            if case_count + span[0] <= span[1]:
                case = format(case_count + span[0], '06')
                break
            else:
                case_count -= span[1] - span[0] + 1
    
    charge = '-' + format(charge_count, '02')
    
    if court in courts_with_fm_case_number:
        case_length = courts_with_fm_case_number[court]
        case = format(case_count, '0' + case_length)
        case_f = str('F' + case).zfill(6)
        case_m = str('M' + case).zfill(6)
        case_numbers.append(prefix + case_f + charge)
        case_numbers.append(prefix + case_m + charge)
    else:
        case_numbers.append(prefix + case + charge)
    
    return case_numbers

def getFilePath(court_name):
    court_name = court_name.replace(' ', '').replace('/', '')
    return '../va-circuit-court-search-files/' + court_name + '/'

def run():
    # Get cookie and list of courts
    cookieJar = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookieJar))
    opener.addheaders = [('User-Agent', user_agent)]
    
    home = opener.open('http://ewsocis1.courts.state.va.us/CJISWeb/circuit.jsp')
    
    courts = []
    html = BeautifulSoup(home.read())
    for option in html.find_all('option'):
        courts.append({
            'fullName': option['value'],
            'id': option['value'][:3],
            'name': option['value'][5:]
        })
    
    courts_recently_completed = []
    with open('courts_recently_completed.txt') as f:
        courts_recently_completed = [x.strip('\n') for x in f.readlines()]
    
    # Go to court
    for index, court in enumerate(courts):
        if court['name'] in courts_recently_completed: continue
        print court['name']
        file_path = getFilePath(court['name'])
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        
        data = urllib.urlencode({
            'courtId': court['id'],
            'courtType': 'C',
            'caseType': 'ALL',
            'testdos': False,
            'sessionCreate': 'NEW',
            'whichsystem': court['fullName']})
        place_url = u"http://ewsocis1.courts.state.va.us/CJISWeb/MainMenu.do"
        opener.open(place_url, data)
        
        # search by case numbers
        sequential_cases_missed_count = 0
        case_count = -1
        file_list = os.listdir(file_path)
        for file_name in file_list:
            if '.html' not in file_name: continue
            cur_count = int(file_name[4:10].split('M')[-1].split('F')[-1])
            if court['name'] in courts_with_continuing_case_numbers:
                last_case = cur_count
                cur_count = 0
                for span in courts_with_continuing_case_numbers[court['name']]:
                    if last_case <= span[1]:
                        cur_count += last_case - span[0]
                        break
                    else:
                        cur_count += span[1] - span[0] + 1
            if cur_count > case_count:
                case_count = cur_count - 1
        
        search_next_case = True
        while search_next_case:
            case_count += 1
            search_next_charge = True
            charge_count = -1
            while search_next_charge:
                charge_count += 1
                if charge_count > 99:
                    break
                case_numbers = get_case_number(court['name'], case_count, charge_count)
                
                for case_number in case_numbers:
                    # get case info
                    data = urllib.urlencode({
                        'categorySelected': 'R',
                        'caseNo': case_number,
                        'courtId': court['id'],
                        'submitValue': ''})
                    cases_url = u"http://ewsocis1.courts.state.va.us/CJISWeb/CaseDetail.do"
                    case_details = opener.open(cases_url, data)
                    html = BeautifulSoup(case_details.read())
                
                    case_exists = html.find(text=re.compile('Case not found')) is None
                    if case_exists:
                        break
                    elif case_number != case_numbers[-1]:
                        print 'Could not find ' + case_number
                
                if case_exists:
                    html_is_invalid = html.find(text=re.compile(case_number)) is None
                    if html_is_invalid:
                        raise Exception('Case detail HTML is invalid')
                    
                    print 'Found ' + case_number
                    sequential_cases_missed_count = 0
                    
                    filename = file_path + case_number + '.html'
                    with open(filename, 'w') as text_file:
                        text_file.write(html.prettify().encode('UTF-8'))
                    
                    data = urllib.urlencode({
                        'categorySelected': 'R',
                        'caseStatus':'A',
                        'caseNo': case_number,
                        'courtId': court['id'],
                        'submitValue': 'P'})
                    case_details = opener.open(cases_url, data)
                    html = BeautifulSoup(case_details.read())
                    html_is_invalid = html.find(text=re.compile(case_number)) is None
                    if html_is_invalid:
                        raise Exception('Case detail pleadings HTML is invalid')
                    filename = file_path + case_number + '_pleadings.html'
                    with open(filename, 'w') as text_file:
                        text_file.write(html.prettify().encode('UTF-8'))
                    
                    data = urllib.urlencode({
                        'categorySelected': 'R',
                        'caseStatus':'A',
                        'caseNo': case_number,
                        'courtId': court['id'],
                        'submitValue': 'S'})
                    case_details = opener.open(cases_url, data)
                    html = BeautifulSoup(case_details.read())
                    html_is_invalid = html.find(text=re.compile(case_number)) is None
                    if html_is_invalid:
                        raise Exception('Case detail services HTML is invalid')
                    filename = file_path + case_number + '_services.html'
                    with open(filename, 'w') as text_file:
                        text_file.write(html.prettify().encode('UTF-8'))
                    
                    data = urllib.urlencode({'courtId': court['id']})
                    opener.open(place_url, data)
                    sleep(1)
                else:
                    print 'Could not find ' + case_number
                    if charge_count > 0:
                        search_next_charge = False
                    if charge_count == 1:
                        sequential_cases_missed_count += 1
                        if sequential_cases_missed_count > 9:
                            search_next_case = False
        
        with open('courts_recently_completed.txt', 'a') as f:
            f.write(court['name'] + '\n')

while True:
    try:
        run()
        break
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        print "Unexpected error:", sys.exc_info()
        print 'Restarting in 30 seconds'
        sleep(30)
print 'Done!'
