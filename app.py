import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
import openfoodfacts
from ourgroceries import OurGroceries
import logging
from evdev import InputDevice, ecodes, categorize, list_devices
import time

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

# Keycode to character mapping
KEYCODE_MAP = {
    ecodes.KEY_0: '0',
    ecodes.KEY_1: '1',
    ecodes.KEY_2: '2',
    ecodes.KEY_3: '3',
    ecodes.KEY_4: '4',
    ecodes.KEY_5: '5',
    ecodes.KEY_6: '6',
    ecodes.KEY_7: '7',
    ecodes.KEY_8: '8',
    ecodes.KEY_9: '9',
    # Add other mappings if needed
}


def get_input_devices():
    devices = []
    input_path = "/dev/input"

    # Verify /dev/input exists
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"{input_path} does not exist")

    # Get all event devices
    event_devices = [f for f in os.listdir(input_path) if f.startswith('event')]

    if not event_devices:
        print("No event devices found in /dev/input")
        return []

    for device in event_devices:
        try:
            dev_path = os.path.join(input_path, device)
            devices.append(InputDevice(dev_path))
        except Exception as e:
            print(f"Couldn't open {dev_path}: {str(e)}")

    return devices

def find_barcode_scanner():
    """Find the barcode scanner input device"""
    devices = [InputDevice(path) for path in list_devices("/dev/input")]
    print(devices)
    for device in devices:
        logger.info(device)
        # Adjust these criteria to match your scanner
        if 'usbscn' in device.name.lower():
            logger.info(f"Found barcode scanner: {device.name} at {device.path}")
            return device.path
    raise Exception("Barcode scanner not found")


async def process_barcode(barcode, og, list_id, api):
    """Process the scanned barcode"""
    try:
        logger.info(f"Processing barcode: {barcode}")
        api_response = api.product.get(barcode, fields=["product_name"])
        product_name = api_response.get("product_name", "Unknown Product")

        if product_name == "Unknown Product":
            logger.warning(f"Product not found for barcode: {barcode}")
            product_name = f"Unknown Product ({barcode})"

        await og.add_item_to_list(
            list_id,
            product_name,
            auto_category=True,
            note="barcode scanned"
        )
        logger.info(f"Added to list: {product_name}")
    except Exception as e:
        logger.error(f"Error processing barcode {barcode}: {str(e)}")


async def read_barcode_events(device, og, list_id, api):
    """Async function to read barcode events"""
    last_barcode = ""
    last_scan_time = 0
    debounce_seconds = 2.0
    current_barcode = []

    try:
        while True:
            # Use asyncio to wait for events without blocking
            await asyncio.sleep(0.01)  # Small delay to prevent CPU overuse

            events = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: [device.read_one() for _ in range(10)]  # Read up to 10 events at once
            )

            for event in filter(None, events):
                if event.type == ecodes.EV_KEY:
                    key_event = categorize(event)
                    if key_event.keystate == 1:  # Key press
                        # Check for enter key (end of barcode)
                        if key_event.scancode == ecodes.KEY_ENTER:
                            if current_barcode:
                                barcode = ''.join(current_barcode)
                                now = time.time()

                                # Debounce check
                                if barcode != last_barcode or (now - last_scan_time) > debounce_seconds:
                                    await process_barcode(barcode, og, list_id, api)
                                    last_barcode = barcode
                                    last_scan_time = now
                                else:
                                    logger.debug(f"Duplicate scan ignored: {barcode}")

                                current_barcode = []
                        else:
                            # Append the digit/character
                            if key_event.scancode in KEYCODE_MAP:
                                current_barcode.append(KEYCODE_MAP[key_event.scancode])
    except Exception as e:
        logger.error(f"Error in scanner loop: {str(e)}")
        raise


async def main():
    load_dotenv()

    username = os.getenv("OURGROCERIES_USERNAME")
    password = os.getenv("OURGROCERIES_PASSWORD")
    list_id = os.getenv("OURGROCERIES_LIST_ID")

    if not all([username, password, list_id]):
        logger.error("Missing required environment variables")
        return

    # Initialize APIs
    og = OurGroceries(username, password)
    await og.login()
    api = openfoodfacts.API(user_agent="BarcodeScannerGroceryList/0.1")

    # Find and open barcode scanner
    device_path = find_barcode_scanner()
    device = InputDevice(device_path)

    logger.info("Barcode scanner service started. Ready to scan...")

    try:
        await read_barcode_events(device, og, list_id, api)
    finally:
        device.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")