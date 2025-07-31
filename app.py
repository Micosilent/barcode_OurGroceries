import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
import openfoodfacts
from ourgroceries import OurGroceries
import sys
import select
import logging
import evdev

# Create log directory in home folder
log_dir = Path.home() / "barcode_scanner_logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "scanner.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    load_dotenv()

    username = os.getenv("OURGROCERIES_USERNAME")
    password = os.getenv("OURGROCERIES_PASSWORD")
    list_id = os.getenv("OURGROCERIES_LIST_ID")

    if not all([username, password, list_id]):
        logger.error("Missing required environment variables")
        sys.exit(1)

    # Initialize APIs
    og = OurGroceries(username, password)
    api = openfoodfacts.API(user_agent="BarcodeScannerGroceryList/0.1")

    # Create async loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(og.login())

    last_input = ""
    debounce_time = 2.0  # seconds to wait for duplicate scans

    logger.info("Barcode scanner service started. Ready to scan...")

    try:
        while True:
            # Use select to wait for input with a timeout
            if select.select([sys.stdin], [], [], 1)[0]:
                barcode_output = sys.stdin.readline().strip()

                if not barcode_output:
                    continue

                # Skip if this is the same as the last scan (debounce)
                if barcode_output == last_input:
                    logger.debug(f"Duplicate scan ignored: {barcode_output}")
                    continue

                logger.info(f"Scanned barcode: {barcode_output}")

                try:
                    # Get product info
                    api_response = api.product.get(barcode_output, fields=["product_name"])
                    product_name = api_response.get("product_name", "Unknown Product")

                    if product_name == "Unknown Product":
                        logger.warning(f"Product not found for barcode: {barcode_output}")

                    # Add to list
                    loop.run_until_complete(
                        og.add_item_to_list(
                            list_id,
                            product_name,
                            auto_category=True,
                            note="barcode scanned"
                        )
                    )

                    logger.info(f"Added to list: {product_name}")
                    last_input = barcode_output

                except Exception as e:
                    logger.error(f"Error processing barcode {barcode_output}: {str(e)}")

    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        loop.close()


if __name__ == "__main__":
    main()