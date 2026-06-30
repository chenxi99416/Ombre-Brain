#!/usr/bin/env python3
"""
Toy Bridge: Telegram → Intiface Central → Lovense Lush
Run on Mac while Intiface Central is running.

Usage:
  pip install buttplug websockets
  python toy-bridge.py

The script connects to Intiface and provides interactive control.
"""

import asyncio
import sys

try:
    from buttplug import Client, WebsocketConnector, ProtocolSpec
    API_VERSION = "new"
except ImportError:
    try:
        from buttplug.client import ButtplugClient, ButtplugClientWebsocketConnector
        API_VERSION = "old"
    except ImportError:
        print("Installing buttplug...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "buttplug"])
        try:
            from buttplug import Client, WebsocketConnector, ProtocolSpec
            API_VERSION = "new"
        except ImportError:
            from buttplug.client import ButtplugClient, ButtplugClientWebsocketConnector
            API_VERSION = "old"

INTIFACE_WS = "ws://127.0.0.1:12345"

client = None
device = None


async def connect():
    global client, device

    if API_VERSION == "new":
        client = Client("OmbreBridge", ProtocolSpec.v3)
        connector = WebsocketConnector(INTIFACE_WS)
    else:
        client = ButtplugClient("OmbreBridge")
        connector = ButtplugClientWebsocketConnector(INTIFACE_WS)

    await client.connect(connector)
    print(f"Connected to Intiface at {INTIFACE_WS} (API: {API_VERSION})")

    await client.start_scanning()
    await asyncio.sleep(2)
    await client.stop_scanning()

    if not client.devices:
        print("No devices found. Make sure Lovense Lush is connected in Intiface.")
        return False

    device = list(client.devices.values())[0]
    print(f"Found device: {device.name}")
    return True


async def vibrate(intensity: float, duration: float = 0):
    """Set vibration intensity (0.0 to 1.0). Duration in seconds (0 = stay on)."""
    if not device:
        print("No device connected")
        return
    clamped = max(0.0, min(1.0, intensity))

    if API_VERSION == "new":
        await device.actuators[0].command(clamped)
    else:
        await device.send_vibrate_cmd(clamped)

    print(f"Vibrate: {clamped:.0%}")
    if duration > 0:
        await asyncio.sleep(duration)
        if API_VERSION == "new":
            await device.actuators[0].command(0)
        else:
            await device.send_vibrate_cmd(0)
        print("Vibrate: off")


async def pattern(steps: list):
    """Play a pattern: [(intensity, duration), ...]"""
    for intensity, duration in steps:
        await vibrate(intensity)
        await asyncio.sleep(duration)
    await vibrate(0)


async def pulse(count=3, intensity=0.8, on_time=0.5, off_time=0.3):
    """Pulse pattern."""
    for _ in range(count):
        await vibrate(intensity)
        await asyncio.sleep(on_time)
        await vibrate(0)
        await asyncio.sleep(off_time)


async def wave():
    """Gradually increase then decrease."""
    for i in range(0, 11):
        await vibrate(i / 10)
        await asyncio.sleep(0.3)
    for i in range(10, -1, -1):
        await vibrate(i / 10)
        await asyncio.sleep(0.3)


async def interactive():
    """Interactive mode for testing."""
    print("\n=== Toy Bridge Interactive Mode ===")
    print("Commands:")
    print("  v <0-100>     Set vibration (e.g., 'v 50' for 50%)")
    print("  pulse [n]     Pulse n times (default 3)")
    print("  wave          Gradual wave pattern")
    print("  off           Stop vibration")
    print("  quit          Exit")
    print()

    loop = asyncio.get_event_loop()

    while True:
        try:
            cmd = await loop.run_in_executor(None, lambda: input("toy> ").strip().lower())
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd:
            continue
        elif cmd == "quit" or cmd == "q":
            break
        elif cmd == "off" or cmd == "0":
            await vibrate(0)
        elif cmd.startswith("v "):
            try:
                val = int(cmd.split()[1])
                await vibrate(val / 100)
            except (ValueError, IndexError):
                print("Usage: v <0-100>")
        elif cmd.startswith("pulse"):
            parts = cmd.split()
            n = int(parts[1]) if len(parts) > 1 else 3
            await pulse(count=n)
        elif cmd == "wave":
            await wave()
        else:
            print(f"Unknown command: {cmd}")

    await vibrate(0)


async def main():
    if not await connect():
        return

    await interactive()

    if client:
        await client.disconnect()
    print("Disconnected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
