#!/usr/bin/env python3
"""
Toy Bridge: Intiface Central → Lovense Lush
Run on Mac while Intiface Central is running.

Usage:
  pip install buttplug websockets
  python toy-bridge.py                          # interactive only
  python toy-bridge.py --relay http://IP:8080   # interactive + remote control
"""

import asyncio
import sys
import json
import urllib.request
import urllib.error

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


async def pulse(count=3, intensity=0.8, on_time=0.5, off_time=0.3):
    for _ in range(count):
        await vibrate(intensity)
        await asyncio.sleep(on_time)
        await vibrate(0)
        await asyncio.sleep(off_time)


async def wave():
    for i in range(0, 11):
        await vibrate(i / 10)
        await asyncio.sleep(0.3)
    for i in range(10, -1, -1):
        await vibrate(i / 10)
        await asyncio.sleep(0.3)


async def escalate():
    """Slow build-up pattern."""
    for level in [0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        await vibrate(level)
        await asyncio.sleep(1.5)
    await vibrate(0)


async def tease():
    """Random-feeling teasing pattern."""
    steps = [0.2, 0.0, 0.3, 0.0, 0.15, 0.0, 0.5, 0.0, 0.1, 0.4, 0.0]
    for s in steps:
        await vibrate(s)
        await asyncio.sleep(0.6)
    await vibrate(0)


async def execute_command(cmd: dict):
    """Execute a remote command dict."""
    action = cmd.get("action", "")
    if action == "vibrate":
        intensity = float(cmd.get("intensity", 0.5))
        duration = float(cmd.get("duration", 0))
        await vibrate(intensity, duration)
    elif action == "pulse":
        count = int(cmd.get("count", 3))
        intensity = float(cmd.get("intensity", 0.8))
        await pulse(count=count, intensity=intensity)
    elif action == "wave":
        await wave()
    elif action == "escalate":
        await escalate()
    elif action == "tease":
        await tease()
    elif action == "off":
        await vibrate(0)
    elif action == "none":
        pass
    else:
        print(f"Unknown remote action: {action}")


async def poll_relay(relay_url: str):
    """Background task: poll relay server for commands."""
    print(f"Polling relay at {relay_url}")
    while True:
        try:
            req = urllib.request.Request(relay_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                cmds = json.loads(resp.read())
                for cmd in cmds:
                    print(f"Remote: {cmd}")
                    await execute_command(cmd)
        except urllib.error.URLError:
            pass
        except Exception as e:
            print(f"Relay error: {e}")
        await asyncio.sleep(1.5)


async def interactive():
    print("\n=== Toy Bridge ===")
    print("Commands:")
    print("  v <0-100>     Set vibration %")
    print("  pulse [n]     Pulse n times")
    print("  wave          Gradual wave")
    print("  escalate      Slow build-up")
    print("  tease         Teasing pattern")
    print("  off           Stop")
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
        elif cmd in ("quit", "q"):
            break
        elif cmd in ("off", "0"):
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
        elif cmd == "escalate":
            await escalate()
        elif cmd == "tease":
            await tease()
        else:
            print(f"Unknown: {cmd}")

    await vibrate(0)


async def main():
    relay_url = None
    if "--relay" in sys.argv:
        idx = sys.argv.index("--relay")
        if idx + 1 < len(sys.argv):
            relay_url = sys.argv[idx + 1]

    if not await connect():
        return

    tasks = [asyncio.create_task(interactive())]
    if relay_url:
        tasks.append(asyncio.create_task(poll_relay(relay_url)))

    await tasks[0]

    if client:
        await client.disconnect()
    print("Disconnected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
