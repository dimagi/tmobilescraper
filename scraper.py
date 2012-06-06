import csv
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
import unittest, time, re
import logging
import sys
from ordereddict import OrderedDict

WP_BALANCES = {}

WP_ERRORS = {}


driver = None
base_url = "http://www.t-mobile.com/"
verificationErrors = []
f = None
writer = None
AREMIND_CSV_FILENAME = "aremind_acc_data2.csv"

import signal
def signal_handler(signal, frame):
        print 'You pressed Ctrl+C!'
        f.close()
        writer.close()
        print 'Here are all the errors:'
        print WP_ERRORS
        sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)


class AccountInfo(object):
    data = None
    def __init__(self):
        data = OrderedDict()
        data["number"] = None
        data["password"] = None
        data["last_login"] = None
        data["successful_login"] = False
        data["current_balance"] = 0.00
        data["expires_on"] = None
        data["is_autorefill"] = False
        data["next_autorefill"] = None
        data["autorefill_amount"] = 0.00
        data["did_autorefill_this_time"] = False
        data["amount_topped_up"] = 0.00
        data["account_locked"] = False
        self.data = data
    def __getitem__(self, attr):
        return self.data[attr]
    def __setitem__(self, key, value):
        self.data[key] = value
    def __str__(self):
        return self.__unicode__()
    def __unicode__(self):
        headers = self.get_headers()
        keys = self.data.keys()
        ret = []
        for i, k in enumerate(keys):
            ret.append('%s: %s' % (headers[i], self[k]))
        return ','.join(ret)
    def to_csv_list(self):
        return self.data.values()
    def get_headers(self):
        return map(lambda x: x.replace('_',' ').title(), self.data.keys())

logger = logging.getLogger('tmobilescraper')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# add formatter to ch
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

DEFAULT_NEW_PASSWORD = "12345Dimagi"

def login_with_creds(acc_info):
    num = acc_info["number"]
    passwd = acc_info["password"]
    logger.debug("Attempting to login for %s" % num)
    driver.get(base_url + "/Login/")
    driver.find_element_by_id("Login1_txtMSISDN").clear()
    driver.find_element_by_id("Login1_txtMSISDN").send_keys(num)
    driver.find_element_by_id("Login1_txtPassword").clear()
    driver.find_element_by_id("Login1_txtPassword").send_keys(passwd)
    driver.find_element_by_id("Login1_chkRemember").click()
    driver.find_element_by_css_selector("#lnkBtnLogin > span").click()

    change_pass_url = "https://my.t-mobile.com//Profile/ChangePassword.aspx?dest=https://my.t-mobile.com/Default.aspx?rp.Logon=true"
    if driver.current_url == change_pass_url:
        logger.debug('The account %s, needs a password change' % num)
        driver.find_element_by_xpath("(//a[@id='A1']/span)[3]").click()
        driver.find_element_by_id("txtOldPassword").click()
        driver.find_element_by_id("txtOldPassword").clear()
        driver.find_element_by_id("txtOldPassword").send_keys(passwd)
        driver.find_element_by_id("txtNewPassword").click()
        driver.find_element_by_id("txtNewPassword").click()
        driver.find_element_by_id("txtNewPassword").clear()
        driver.find_element_by_id("txtNewPassword").send_keys(DEFAULT_NEW_PASSWORD)
        driver.find_element_by_id("txtConfirmPassword").clear()
        driver.find_element_by_id("txtConfirmPassword").send_keys(DEFAULT_NEW_PASSWORD)
        driver.find_element_by_id("recaptcha_response_field").click()
        driver.find_element_by_id("recaptcha_response_field").clear()
        recaptcha_input = raw_input("PLEASE ENTER THE CAPTCHA INPUT IN THE BROWSER THEN PRESS ENTER HERE: ")
        driver.find_element_by_css_selector("#btnSaveChanges > span.ftxt11").click()
        logger.info("Account password succesfully changed!")
        acc_info["password"] = DEFAULT_NEW_PASSWORD

    acc_info["successful_login"] = True
    acc_info["last_login"] = datetime.datetime.now()


def logout_current_account():
    logger.debug('Attempting to log out of current session...')
    driver.get(base_url + "/logout.aspx")
    # driver.find_element_by_css_selector("li.last > a > span").click()
    logger.debug('Probably successful')

def get_thing(page_url, css_selector):
    if driver.current_url != page_url:
        driver.get(page_url)
    element = driver.find_element_by_css_selector(css_selector)
    return element.text.strip()

def get_thing_by_xpath(page_url, xpath):
    if driver.current_url != page_url:
        driver.get(page_url)
    element = driver.find_element_by_xpath(xpath)
    return element.text.strip()


def get_current_balance(acc_info):
    balance = get_thing('https://my.t-mobile.com/Default.aspx?rp.Logon=true', "html body form#WebForm1 div#wrapper.region1 div#page.home div#myaccount-module.topPanel div#eventssummary.myaccount-mod-body div.dynamic-height div#pp_prepaidbalance.myaccount-mod-div div.myaccount-mod-desc")
    balance = balance.strip('$')
    logger.debug('Found balance for %s: $%s' % (acc_info["number"], balance))
    return balance

def get_expiry_date(acc_info):
    expiry_date = get_thing('https://my.t-mobile.com/Default.aspx?rp.Logon=true', "html body form#WebForm1 div#wrapper.region1 div#page.home div#myaccount-module.topPanel div#eventssummary.myaccount-mod-body div.dynamic-height div#pp_useBy.myaccount-mod-div div.myaccount-mod-desc")
    logger.debug('Found expiry_date for %s: %s' % (acc_info["number"], expiry_date))
    return expiry_date

def is_on_autorefill(acc_info):
    topup_settings_page = 'https://my.t-mobile.com/PartnerServices.aspx?service=vesta_autorefill'
    refill_freq = get_thing_by_xpath(topup_settings_page, "/html/body/div/div[2]/div/div/div[3]/div/div/div/div[4]/div/div[9]/span[2]")
    logger.debug("Refill Freq is: %s" % refill_freq)
    auto_refill_amount = get_thing_by_xpath(topup_settings_page, "/html/body/div/div[2]/div/div/div[3]/div/div/div/div[4]/div/div[11]/span[2]/font")
    acc_info["autorefill_amount"] = auto_refill_amount
    return refill_freq and refill_freq == "Monthly"

def topup_acc_with(amount, acc_info):
    refill_url = 'https://my.t-mobile.com/PartnerServices.aspx?source=mytmobile&service=vesta_credit'
    if driver.current_url != refill_url:
        driver.get(refill_url)
    driver.find_element_by_id("opendenominationamount").clear()
    driver.find_element_by_id("opendenominationamount").send_keys(str(amount))
    driver.find_element_by_id("emailAddressOut").clear()
    driver.find_element_by_id("emailAddressOut").send_keys("admin@dimagi.com")
    driver.find_element_by_id("ButtonContinue").click()
    _input = raw_input("Was the topup succesfull? (y/n)")
    if _input.lower() == "y":
        acc_info["did_autorefill_this_time"] = True
        acc_info["amount_topped_up"] = amount
    else:
        acc_info["did_autorefill_this_time"] = False
        acc_info["amount_topped_up"] = 0.00

def ask_should_topup(acc_info):
    should_topup = raw_input("The account '%s' has a current balance of $%s. Do you want to top it up? (y/n)" % (acc_info["number"], acc_info["current_balance"]))
    should_topup = should_topup.lower()
    if should_topup == "y":
        return True
    elif should_topup == "n":
        return False
    else:
        return -1

def load_accs_from_csv(filename):
    logger.debug('Loading info from %s' % filename)
    retlist = []
    try:
        infile = open(filename,'rb')
        logger.debug('%s loaded' % infile)
    except IOError:
        logger.debug('COULD NOT FIND FILE WITH NAME %s' % filename)
        raise

    reader = csv.reader(infile)
    reader.next() #skip header row
    for row in reader:
        logger.debug('Parsing row: %s' % row)
        acc_info = AccountInfo()
        acc_info["number"] = row[0]
        acc_info["password"] = row[1]
        acc_info["last_login"] = row[2]
        acc_info["successful_login"] = row[3].lower() == "true"
        acc_info["current_balance"] = row[4]
        acc_info["expires_on"] = row[5]
        acc_info["is_autorefill"] = row[6].lower() == "true"
        acc_info["next_autorefill"] = row[7]
        acc_info["autorefill_amount"] = row[8]
        acc_info["did_autorefill_this_time"] = row[9].lower() == "true"
        acc_info["amount_topped_up"] = row[10]
        acc_info["account_locked"] = row[11].lower() == "true"
        logger.debug('Parsed as: %s' % acc_info.to_csv_list())
        retlist.append(acc_info)

    logger.debug('Successfully parsed %s' % filename)
    infile.close()
    return retlist



def ask_topup_amount(acc_info):
    amt = raw_input("Please enter the dollar amount [MINIMUM 10 DOLLARS] (number only!)")
    try:
        amt = int(amt)
    except ValueError:
        amt = float(amt)
        #if this fails it should bubble up and stop the script.

    if amt<10:
        amt = raw_input("Amount to refill must be >= $10.  T-Mobile does not allow smaller refill amounts. Enter refill amount:")
        try:
            amt = int(amt)
        except ValueError:
            amt = float(amt)
            #if this fails it should bubble up and stop the script.

    return amt

def start():
    logger.info('Attempting to get Balance information for all accounts...')
    WP_ITEMS = []
    accounts = load_accs_from_csv(AREMIND_CSV_FILENAME) #list of AccountInfo objects


    outfile = open(AREMIND_CSV_FILENAME, 'wb')
    writer = csv.writer(outfile)
    writer.writerow(AccountInfo().get_headers())
    for acc_info in accounts:
            WP_ITEMS.append(acc_info)
            if acc_info["account_locked"]:
                logger.debug("Skipping account %s, marked as locked (we don't know the password)" % acc_info["number"])
                WP_ERRORS.update({acc_info["number"]: "ACCOUNT_MARKED_LOCKED"})
                continue
            login_with_creds(acc_info)
            if driver.current_url != 'https://my.t-mobile.com/Default.aspx?rp.Logon=true':
                    #assume incorrect password
                    WP_ERRORS.update({acc_info["number"]: "WRONG_PASSWORD"})
                    acc_info["successful_login"] = False
                    acc_info["account_locked"] = True #We shouldn't try any more attempts on this account or t-mobile gets pissed and locks us out.
                    logger.debug("Couldn't log into account: %s!" % acc_info["number"])
                    _input = raw_input("Try again? (y/n):")
                    if _input.lower() == "y":
                        _input = raw_input("Please login manually. Was it succesful? (y/n)")
                        if _input.lower() == "n":
                            continue
                    else:
                        continue
            acc_info["current_balance"] = get_current_balance(acc_info)
            acc_info["expires_on"] = get_expiry_date(acc_info)
            acc_info["is_autorefill"] = is_on_autorefill(acc_info)
            logger.debug("is_on_autorefill result: %s" % acc_info["is_autorefill"])
            if not acc_info["is_autorefill"]:
                logger.error("WARNING ACCOUNT DOES NOT HAVE AUTO_REFILL!: %s. Details: %s" % (acc_info["number"], acc_info.__unicode__))

#            should_topup = -1
#            while should_topup==-1:
#                should_topup = ask_should_topup(acc_info)
#
#            if should_topup:
#                amt = ask_topup_amount(acc_info)
#                logger.debug('Attempting to refill account %s, with $%s' % (acc_info["number"], amt))
#                topup_acc_with(amt, acc_info)

            logout_current_account()
            logger.debug('CSV Output: %s' % acc_info.to_csv_list())
            writer.writerow(acc_info.to_csv_list())


    outfile.close()

if __name__=="__main__":
    logger.info("Launching T-Mobile Scraper")
    driver = webdriver.Firefox()
    driver.implicitly_wait(30)
    start()

    driver.quit()
    sys.exit()