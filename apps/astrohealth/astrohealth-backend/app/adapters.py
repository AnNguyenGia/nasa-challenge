"""Optional local sensor bridges. Each adapter publishes the same validated MQTT packet contract."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

from app.core import canonical, settings
from app.telemetry import Measurement


async def file_replay(path: Path) -> AsyncIterator[dict[str, Any]]:
    """Replay newline JSON; retain original UTC/source rather than forging live measured data."""
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield Measurement.model_validate_json(line).model_dump(mode="json")
                await asyncio.sleep(0.01)


async def udp_packets(port: int) -> AsyncIterator[dict[str, Any]]:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", port))
    sock.setblocking(False)
    try:
        while True:
            packet, _ = await asyncio.get_running_loop().sock_recvfrom(sock, 65536)
            yield Measurement.model_validate_json(packet).model_dump(mode="json")
    finally:
        sock.close()


async def serial_packets(port: str) -> AsyncIterator[dict[str, Any]]:
    import serial

    with serial.Serial(port, baudrate=115200, timeout=1) as device:
        while True:
            packet = await asyncio.to_thread(device.readline)
            if packet:
                yield Measurement.model_validate_json(packet).model_dump(mode="json")


async def ble_packets(address: str, characteristic: str) -> AsyncIterator[dict[str, Any]]:
    from bleak import BleakClient

    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

    def notified(_: Any, packet: bytearray) -> None:
        # Loss is explicit; crashing this adapter allows the supervisor/operator to investigate.
        queue.put_nowait(bytes(packet))

    async with BleakClient(address) as device:
        await device.start_notify(characteristic, notified)
        while True:
            yield Measurement.model_validate_json(await queue.get()).model_dump(mode="json")


async def bridge(args: argparse.Namespace) -> None:
    import aiomqtt

    source = (
        file_replay(Path(args.address))
        if args.transport == "file"
        else udp_packets(int(args.address))
        if args.transport == "udp"
        else serial_packets(args.address)
        if args.transport == "serial"
        else ble_packets(args.address, args.characteristic)
    )
    async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
        async for packet in source:
            await client.publish("astrohealth/measurements", canonical(packet), qos=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local AstroHealth sensor-to-MQTT adapter")
    parser.add_argument("transport", choices=["file", "udp", "serial", "ble"])
    parser.add_argument("address", help="File path, loopback UDP port, serial port, or BLE device address")
    parser.add_argument("--characteristic", default="")
    args = parser.parse_args()
    if __import__("sys").platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(bridge(args))


if __name__ == "__main__":
    main()
