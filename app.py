import asyncio
import os

import openfoodfacts
from ourgroceries import OurGroceries

from dotenv import load_dotenv

load_dotenv()

username = os.getenv("OURGROCERIES_USERNAME")
password = os.getenv("OURGROCERIES_PASSWORD")
list_id = os.getenv("OURGROCERIES_LIST_ID")

og = OurGroceries(username, password)

loop = asyncio.get_event_loop()
loop.run_until_complete(og.login())


api = openfoodfacts.API(user_agent="BarcodeScannerGroceryList/0.1")
last_input = ""
while True:
    #Wait for a barcode input
    barcode_output = input()
    if barcode_output == last_input:
        continue
    else:
        api_response = api.product.get(barcode_output, fields=["product_name"])
        loop.run_until_complete(og.add_item_to_list(list_id, api_response["product_name"], auto_category=True, note="barcode scanned"))
        last_input = barcode_output

    print(api_response)

