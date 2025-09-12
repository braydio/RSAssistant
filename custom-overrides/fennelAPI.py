import asyncio
import os
import traceback

from dotenv import load_dotenv
from fennel_invest_api import Fennel

from helperAPI import (
    Brokerage,
    getOTPCodeDiscord,
    printAndDiscord,
    printHoldings,
    stockOrder
)


import os
import traceback
import logging
import asyncio
from dotenv import load_dotenv
from fennel_invest_api.fennel import Fennel, Brokerage

# Configure logging to show debug messages.
logging.basicConfig(level=logging.DEBUG)

def get_otp_and_login(fb, account, name, botObj, loop):
    """
    Retrieve the OTP code from Discord and attempt login.
    """
    timeout = 300  # seconds
    logging.debug(f"{name}: Waiting for OTP code from Discord (timeout: {timeout}s)...")
    otp_code = asyncio.run_coroutine_threadsafe(
        getOTPCodeDiscord(botObj, name, timeout=timeout, loop=loop),
        loop,
    ).result()
    logging.debug(f"{name}: Received OTP code: {otp_code}")
    if otp_code is None:
        raise Exception("No 2FA code found")
    # Log the OTP code before using it (be careful with logging sensitive data in production)
    logging.debug(f"{name}: Attempting login with OTP code: {otp_code}")
    fb.login(email=account, wait_for_code=False, code=otp_code)

def fennel_init(FENNEL_EXTERNAL=None, botObj=None, loop=None):
    load_dotenv()
    fennel_obj = Brokerage("Fennel")
    if not os.getenv("FENNEL") and FENNEL_EXTERNAL is None:
        logging.info("Fennel not found in .env, skipping initialization...")
        return None
    FENNEL = (
        os.environ["FENNEL"].strip().split(",")
        if FENNEL_EXTERNAL is None
        else FENNEL_EXTERNAL.strip().split(",")
    )
    logging.info("Starting login process for Fennel accounts...")
    for index, account in enumerate(FENNEL):
        name = f"Fennel {index + 1}"
        try:
            logging.info(f"{name}: Attempting login for email: {account}")
            fb = Fennel(filename=f"fennel{index + 1}.pkl", path="./creds/")
            try:
                if botObj is None and loop is None:
                    logging.debug(f"{name}: Logging in from CLI (waiting for OTP if required)...")
                    fb.login(email=account, wait_for_code=True)
                else:
                    logging.debug(f"{name}: Logging in from Discord (not waiting for OTP initially)...")
                    fb.login(email=account, wait_for_code=False)
            except Exception as e:
                if "2FA" in str(e) and botObj is not None and loop is not None:
                    logging.info(f"{name}: 2FA required, retrieving OTP via Discord...")
                    get_otp_and_login(fb, account, name, botObj, loop)
                else:
                    logging.error(f"{name}: Error during initial login attempt: {e}")
                    raise e

            # Log that login was accepted and we are retrieving account IDs
            logging.debug(f"{name}: Login accepted, retrieving account IDs...")
            account_ids = fb.get_account_ids()
            logging.debug(f"{name}: Account IDs received: {account_ids}")
            fennel_obj.set_logged_in_object(name, fb, "fb")
            
            for i, an in enumerate(account_ids):
                account_name = f"Account {i + 1}"
                logging.debug(f"{name}: Retrieving portfolio summary for {account_name} (account id: {an})...")
                b = fb.get_portfolio_summary(an)
                fennel_obj.set_account_number(name, account_name)
                fennel_obj.set_account_totals(
                    name,
                    account_name,
                    b["cash"]["balance"]["canTrade"],
                )
                fennel_obj.set_logged_in_object(name, an, account_name)
                logging.info(f"{name}: Found {account_name}")
            logging.info(f"{name}: Logged in successfully")
        except Exception as e:
            logging.error(f"{name}: Error logging into Fennel: {e}")
            logging.error(traceback.format_exc())
            continue
    logging.info("Finished logging into Fennel!")
    return fennel_obj



def fennel_holdings(fbo: Brokerage, loop=None):
    for key in fbo.get_account_numbers():
        for account in fbo.get_account_numbers(key):
            obj: Fennel = fbo.get_logged_in_objects(key, "fb")
            account_id = fbo.get_logged_in_objects(key, account)
            try:
                # Get account holdings
                positions = obj.get_stock_holdings(account_id)
                if positions != []:
                    for holding in positions:
                        qty = holding["investment"]["ownedShares"]
                        if float(qty) == 0:
                            continue
                        sym = holding["security"]["ticker"]
                        cp = holding["security"]["currentStockPrice"]
                        if cp is None:
                            cp = "N/A"
                        fbo.set_holdings(key, account, sym, qty, cp)
            except Exception as e:
                printAndDiscord(f"Error getting Fennel holdings: {e}")
                print(traceback.format_exc())
                continue
    printHoldings(fbo, loop, False)


def fennel_transaction(fbo: Brokerage, orderObj: stockOrder, loop=None):
    print()
    print("==============================")
    print("Fennel")
    print("==============================")
    print()
    for s in orderObj.get_stocks():
        for key in fbo.get_account_numbers():
            printAndDiscord(
                f"{key}: {orderObj.get_action()}ing {orderObj.get_amount()} of {s}",
                loop,
            )
            for account in fbo.get_account_numbers(key):
                obj: Fennel = fbo.get_logged_in_objects(key, "fb")
                account_id = fbo.get_logged_in_objects(key, account)
                try:
                    order = obj.place_order(
                        account_id=account_id,
                        ticker=s,
                        quantity=orderObj.get_amount(),
                        side=orderObj.get_action(),
                        dry_run=orderObj.get_dry(),
                    )
                    if orderObj.get_dry():
                        message = "Dry Run Success"
                        if not order.get("dry_run_success", False):
                            message = "Dry Run Failed"
                    else:
                        message = "Success"
                        if order.get("data", {}).get("createOrder") != "pending":
                            message = order.get("data", {}).get("createOrder")
                    printAndDiscord(
                        f"{key}: {orderObj.get_action()} {orderObj.get_amount()} of {s} in {account}: {message}",
                        loop,
                    )
                except Exception as e:
                    printAndDiscord(f"{key} {account}: Error placing order: {e}", loop)
                    print(traceback.format_exc())
                    continue
