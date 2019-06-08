#!/usr/bin/env python3
import requests
import logging
import pandas as pd
from html.parser import HTMLParser
import re
import sqlite3
import argparse

PROG_DESCRIPTION = "Create a local copy of the Dan Murphy's product database and draw some meaningful information from it"

BASE_API_URL = "https://api.danmurphys.com.au/apis/ui/Browse"
IMAGE_URL = "https://media.danmurphys.com.au/dmo/product/"
PRODUCT_URL = "https://www.danmurphys.com.au/product/DM_"
USER_AGENT = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0"

# The overarching product types
PRODUCT_TYPES = ["spirits", "white wine",
                 "champagne-sparkling", "whisky", "red wine", "beer", "cider"]
# Products that have been introduced in error
DISALLOWED_PRODUCTS = ["TASTING, BITTERS", "GIFT"]

# What identifies as a 'single' or a 'case'
SINGLE_KEYS = ["BOTTLE", "PACK", "EACH", "CAN", "CASK"]
CASE_KEYS = ["CASE"]
ACCEPTABLE_RATIO = 3.5

# All the required fields we must gather to make meaningful conclusions
REQ_FIELDS = ["Stockcode", "Prices", "UrlFriendlyName",
              "AdditionalDetails", "AvailablePackTypes"]
REQ_ADDITIONAL_DETAILS = ["producttitle", "webliquorsize",
                          "standarddrinks", "image1"]

# File locations
ERROR_LOG = "logs/danppss_error.log"
TEST_DB = "data/testDB.db"
PROD_DATABASE = "data/danDB.db"

reqHeaders = {
    "User-Agent": USER_AGENT,
    "Host": "api.danmurphys.com.au",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json",
}

# Handle Arguments
parser = argparse.ArgumentParser(description=PROG_DESCRIPTION)
parser.add_argument("-v", "--verbose", action="store_true")
parser.add_argument("-t", "--test", action="store_true")
args = parser.parse_args()

# Set up the two loggers
logger = logging.getLogger("DanPPSS")
if args.verbose:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)
errorHandler = logging.FileHandler(ERROR_LOG)
errorHandler.setLevel(logging.ERROR)
debugHandler = logging.StreamHandler()
debugHandler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
errorHandler.setFormatter(formatter)
debugHandler.setFormatter(formatter)
logger.addHandler(errorHandler)
logger.addHandler(debugHandler)

class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def buildParams(department, pageNumber, pageSize=100, sortType="Relevance"):
    return {
        "department": department,
        "filters": [],
        "pageNumber": pageNumber,
        "pageSize": pageSize,
        "sortType": sortType,
        "Location": "ListerFacet"
    }

# 1 Unit | 36 Standards | Ratio : 
# 10 Units | 19 Standards | Ratio:

# (Standards x units) / price = Golden Number

def testFields(product):
    additionalDetails = product["AdditionalDetails"]
    # If the product has all of the neccessary additional attributes
    if set(REQ_ADDITIONAL_DETAILS).issubset([detail["Name"] for detail in additionalDetails]):
        # If the product contains neccessary basic information
        if set(REQ_FIELDS).issubset(list(product.keys())):
            # If the product is purchasable
            if (product["IsPurchasable"] and (product["IsForCollection"] or product["IsForDelivery"])):
                # If the product is disallowed
                if not (product["Stockcode"] in DISALLOWED_PRODUCTS):
                    for dissallowed in DISALLOWED_PRODUCTS:
                        if dissallowed in product["Description"]:
                            logger.debug("Product is dissallowed, disregarding {}".format(product["Description"]))
                            return False
                    return True
                else:
                    logger.debug("Product is dissallowed, disregarding {}".format(product["Description"]))
                    return False
            else:
                logger.debug("Product is non-purchasable, disregarding {}".format(product["Description"]))
                return False
        else:
            logger.debug("Product has not all basic attributes, disregarding {}".format(product["Description"]))
            return False
    else:
        logger.debug("Product has not all additional attributes, disregarding {}".format(product["Description"]))
        return False

    return True


def sendToDatabase(frame, path):
    try:
        cnx = sqlite3.connect(path)
    except:
        return False
    c = cnx.cursor()
    c.execute("DROP TABLE IF EXISTS DanDB")
    frame.to_sql(name="DanDB", con=cnx)
    cnx.commit()
    cnx.close()
    logger.info("Sent to database: {}".format(path))
    return True


def showStats(frame):
    print("--------------------------- Statistics ---------------------------\n")
    print("{} \n".format(frame["SinglePricePerStandard"].describe()))
    print("{} \n".format(frame["CasePricePerStandard"].describe()))
    # print("\nMax Single PPS {}".format(frame.loc[frame["SinglePricePerStandard"].idxmax()]))
    # print("\nMax Case PPS {}\n".format(frame.loc[frame["CasePricePerStandard"].idxmax()]))


def buildProductFromData(product, department):
    # Get the very basic information of the product
    usefulProduct = {
        "Type": department,
        "Stockcode": product["Stockcode"],
        "UrlFriendlyName": product["UrlFriendlyName"],
        "AverageRating": 0,
        "ReviewCount": 0,
        "SinglePrice": None,
        "CasePrice": None,
        "SinglePriceAmount": None,
        "CasePriceAmount": None,
        "SingleMessage": None,
        "CaseMessage": None,
        "Promo": False,
        "Description":None,
        "DirectFromSupplier":False
    }

    # Get additional info from the product
    for detail in product["AdditionalDetails"]:
        if detail["Name"] in REQ_ADDITIONAL_DETAILS:
            usefulProduct[detail["Name"]] = detail["Value"]
        elif detail["Name"] == "webaverageproductrating":
            usefulProduct["AverageRating"] = float(detail["Value"])
        elif detail["Name"] == "webtotalreviewcount":
            usefulProduct["ReviewCount"] = int(detail["Value"])
        elif detail["Name"] == "webdescriptionshort":
            usefulProduct["Description"] = detail["Value"]
    
    # Set the flag for if the product comes from the supplier
    if "ER_" in usefulProduct["Stockcode"]:
        usefulProduct["DirectFromSupplier"] = True

    ## Get out the SinglePrice, CasePrice, SinglePriceAmount, CasePriceAmount

    # If the product is sold in singles
    if "singleprice" in product["Prices"]:
        # Get the quantity out
        try:
            usefulProduct["SinglePriceAmount"] = int(re.findall(r'\d+', product["Prices"]["singleprice"]["Message"])[0])
            usefulProduct["SinglePrice"] = float(product["Prices"]["singleprice"]["Value"])
            usefulProduct["SingleMessage"] = product["Prices"]["singleprice"]["Message"]
        # If that fails, its 1 unit assummed
        except:
            usefulProduct["SinglePriceAmount"] = 1
            usefulProduct["SinglePrice"] = float(product["Prices"]["singleprice"]["Value"])
            usefulProduct["SingleMessage"] = product["Prices"]["singleprice"]["Message"]
    
    # If the product is sold in cases
    if "caseprice" in product["Prices"]:
        # Get the quantity out
        try:
            usefulProduct["CasePriceAmount"] = int(re.findall(r'\d+', product["Prices"]["caseprice"]["Message"])[0])
            usefulProduct["CasePrice"] = float(product["Prices"]["caseprice"]["Value"])
            usefulProduct["CaseMessage"] = product["Prices"]["caseprice"]["Message"]
        # If that fails, its 1 unit assummed
        except:
            usefulProduct["CasePriceAmount"] = 1
            usefulProduct["CasePrice"] = float(product["Prices"]["caseprice"]["Value"])
            usefulProduct["CaseMessage"] = product["Prices"]["caseprice"]["Message"]

    if "promoprice" in product["Prices"]:
        try:
            amountForPromo = int(re.findall(r'\d+', product["Prices"]["promoprice"]["Message"])[0])
        except:
            amountForPromo = 1
        # If the promo is for a single
        if amountForPromo == usefulProduct["SinglePriceAmount"]:
            usefulProduct["SinglePriceAmount"] = amountForPromo
            usefulProduct["SinglePrice"] = float(product["Prices"]["promoprice"]["Value"])
            usefulProduct["SingleMessage"] = product["Prices"]["promoprice"]["Message"]
            usefulProduct["Promo"] = True
        # If the promo is for a case
        if amountForPromo == usefulProduct["CasePriceAmount"]:
            usefulProduct["CasePriceAmount"] = amountForPromo
            usefulProduct["CasePrice"] = float(product["Prices"]["promoprice"]["Value"])
            usefulProduct["CaseMessage"] = product["Prices"]["promoprice"]["Message"]
            usefulProduct["Promo"] = True


    # If prices and amounts could not be accertained for either case or single disregard
    if not (usefulProduct["SinglePrice"] or usefulProduct["CasePrice"]):
        logger.debug("Prices are not set for either single or case, disregarding")
        return False

    return cleanProduct(usefulProduct)
        
def cleanProduct(builtProduct):
    if "Description" in builtProduct:
        if builtProduct["Description"] != None:
            builtProduct["Description"] = strip_tags(builtProduct["Description"])

    builtProduct["standarddrinks"] = re.sub(
        r"[\(\[].*?[\)\]]", "", builtProduct["standarddrinks"]).strip()
    
    # If the price per standard is in terms of two seperate units (like a twin pack) or a multiple (1.0 x 10 units)
    if "/" in builtProduct["standarddrinks"]:
        twoQuantites = builtProduct["standarddrinks"].replace(" ", "").split("/")
        try:
            builtProduct["standarddrinks"] = float(twoQuantites[0]) + float(twoQuantites[1])
            builtProduct["SinglePriceAmount"] = 1
        except:
            logger.debug("Multi product cannot be split and reformed, disregarding {}".format(builtProduct["producttitle"]))
            return False

    elif "x" in builtProduct["standarddrinks"]:
        try:
            twoQuantites = builtProduct["standarddrinks"].replace(" ", "").split("x")
            if twoQuantites[0] > twoQuantites[1]:
                builtProduct["standarddrinks"] = twoQuantites[1]
            else:
                builtProduct["standarddrinks"] = twoQuantites[0]
        except:
            logger.debug("Unit containing 'x' cannot be reformed, disregarding {}".format(builtProduct["producttitle"]))
            return False
    try:
        builtProduct["standarddrinks"] = float(builtProduct["standarddrinks"])
    except:
        logger.debug("Standard drinks unit cannot be converted to float, disregarding {}".format(builtProduct["producttitle"]))
        return False

    return builtProduct


def addComplementaryData(product):
    # Build the image and fully qualified product URL
    product["ImageUrl"] = IMAGE_URL+product["image1"]
    product["ProductUrl"] = PRODUCT_URL + \
        product["Stockcode"]+"/"+product["UrlFriendlyName"]

    # The moment of truth, calculate price per standard for a listing
    # Price per standard = price per individual item / price per standard

    # Sometimes the API will return the total amount of standards in a pack
    # rather than standards per actual unit. This is a crude way of getting
    # around that

    # Disregard bitters, as their alcohol content is so low its hard to tell if its over 
    # or under the golden number

    if all([product["SinglePriceAmount"], product["SinglePrice"]]):
        goldenNumber = (product["standarddrinks"] * product["SinglePriceAmount"]) / product["SinglePrice"]
        if(goldenNumber > ACCEPTABLE_RATIO and (product["Type"] not in ["red wine", "white wine"])):
            logger.debug("Product is over the golden number (for single/case), disregarding {}".format(product["producttitle"]))
            return False
    
    if all([product["CasePriceAmount"], product["CasePrice"]]):
        goldenNumber = (product["standarddrinks"] * product["CasePriceAmount"]) / product["CasePrice"]
        # Red and white wine is so cheap, high alcohol content and sold in 
        # little units it looks like an error, so ignore them in the test
        if(goldenNumber > ACCEPTABLE_RATIO and (product["Type"] not in ["red wine", "white wine"])):
            logger.debug("Product is over the golden number (for case), disregarding {}".format(product["producttitle"]))
            return False

    try:
        product["CasePricePerStandard"] = (
            product["CasePrice"] / product["CasePriceAmount"]) / product["standarddrinks"]
    except (TypeError, ZeroDivisionError):
        product["CasePricePerStandard"] = None
    try:
        product["SinglePricePerStandard"] = (
            product["SinglePrice"] / product["SinglePriceAmount"]) / product["standarddrinks"]
    except (TypeError, ZeroDivisionError):
        product["SinglePricePerStandard"] = None

    if product["CasePricePerStandard"] == 0:
        product["CasePricePerStandard"] = None
        product["CasePrice"] = None
        product["CasePriceAmount"] = None
    
    if product["SinglePricePerStandard"] == 0:
        product["SinglePricePerStandard"] = None
        product["SinglePrice"] = None
        product["SinglePriceAmount"] = None

    if product["CasePricePerStandard"] == None and product["SinglePricePerStandard"] == None:
        logger.debug("No price per standard can be calculated for either case or single, disregarding {}".format(product["producttitle"]))
        return False

    return product


def main(testing=False):
    logger.info("Starting the shadow...")
    productsPassed = []
    totalProductsIndexed = 0
    parseFailCount = 0
    fieldFailCount = 0
    for department in PRODUCT_TYPES:
        logger.info(
            "Retreiving products in the '{}' department".format(department))
        pageNumber = 1
        while True:
            logger.debug("Retreiving page {} of '{}'".format(
                pageNumber, department))
            req = requests.post(
                BASE_API_URL, json=buildParams(department, pageNumber))
            # If the API returns an error, skip to the next department
            if req.status_code != 200:
                break
            res = req.json()
            # If there are no products to return, the pageNumber has been exceeded
            if len(res["Bundles"]) <= 0:
                break
            for bundle in res["Bundles"]:
                # Index a product
                totalProductsIndexed += 1
                product = bundle["Products"][0]
                # Test if the product has the data required to be useful
                if testFields(product):
                    usefulProduct = buildProductFromData(product, department)
                    if usefulProduct and addComplementaryData(usefulProduct):
                        productsPassed.append(
                            addComplementaryData(usefulProduct))
                    else:
                        # The product could not be parsed for all data (probably due to a pricing error), go to next product
                        parseFailCount += 1
                        continue
                else:
                    # If the product could not be parsed for neccessary fields, go to the next one
                    fieldFailCount += 1
                    continue

            # If we are testing, stop after 2 pages
            if testing and pageNumber == 5:
                df = pd.DataFrame(productsPassed)
                sample = df.sample(n=50)
                sendToDatabase(sample, TEST_DB)
                logger.info("Retreived a page with {} total indexed, {} products with missing fields, and {} parse errors".format(
                    totalProductsIndexed, fieldFailCount, parseFailCount))
                showStats(sample)
                print(sample)
                return True

            # Go to the next page
            pageNumber = pageNumber + 1

    logger.info("SUCCESSS! Retreived all products")
    logger.info("Retreived a page with {} total indexed, {} products with missing fields, and {} parse errors".format(
        totalProductsIndexed, fieldFailCount, parseFailCount))
    frame = pd.DataFrame(productsPassed)
    sortedFrame = frame.sort_values(by=["SinglePricePerStandard", "CasePricePerStandard"]).reset_index(drop=True)
    sendToDatabase(sortedFrame, PROD_DATABASE)
    showStats(sortedFrame)

if __name__ == "__main__":
    main(testing=args.test)