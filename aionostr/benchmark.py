"""
Run these benchmarks like so:

aionostr bench -r ws://localhost:6969 -f events_per_second -c 2

Available benchmarks:
    events_per_second: measures reading events
    req_per_second: measures total time from subscribing, reading, to unsubscribing
    adds_per_second: measures time to add events
"""
import asyncio
import secrets

from time import perf_counter
from aionostr.event import Event
from aionostr.key import PrivateKey
from aionostr.relay import Relay


class catchtime:
    __slots__ = ("start", "count", "duration")

    def __enter__(self):
        self.start = perf_counter()
        self.count = 0
        return self

    def __exit__(self, type, value, traceback):
        self.duration = perf_counter() - self.start

    def __add__(self, value):
        self.count += value
        return self

    def throughput(self):
        return self.count / self.duration


def make_events(num_events):
    private_key = PrivateKey()
    pubkey = private_key.public_key.hex()
    prikey = private_key.hex()
    events = []
    for i in range(num_events):
        e = Event(kind=22222, content=secrets.token_hex(6), pubkey=pubkey)
        e.sign(prikey)
        events.append(e)
    return events


async def adds_per_second(url, num_events=100):
    relay = Relay(url)
    events = make_events(num_events)
    async with relay:
        with catchtime() as timer:
            for e in events:
                await relay.add_event(e, check_response=True)
                timer += 1
    print(f"\tAdd: took {timer.duration:.2f} seconds. {timer.throughput():.1f}/sec")
    return timer.throughput()


async def events_per_second(url, kind=22222, limit=500, duration=20):
    relay = Relay(url)
    query = {"kinds": [kind], "limit": limit}
    async with relay:
        with catchtime() as timer:
            queue = await relay.subscribe("bench", query)
            while True:
                event = await queue.get()
                if event is None:
                    break
                timer += 1
        await relay.unsubscribe("bench")
    print(
        f"\tEvents: took {timer.duration:.2f} seconds. {timer.throughput():.1f}/sec {timer.count}"
    )
    return timer.throughput()

async def req_per_second(url, kind=22222, limit=50, duration=20):
    query = {"kinds": [kind], "limit": limit}
    relay = Relay(url)
    async with relay:
        stoptime = perf_counter() + duration
        i = 0
        with catchtime() as timer:
            while perf_counter() < stoptime:
                queue = await relay.subscribe(f"bench{i}", query)
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                timer += 1
                await relay.unsubscribe(f"bench{i}")
                i += 1
    print(
        f"\tReq: {timer.count} iterations. {timer.throughput():.1f}/sec"
    )
    return timer.throughput()


async def runner(concurrency, func, *args, **kwargs):
    tasks = []
    for i in range(concurrency):
        tasks.append(asyncio.create_task(func(*args, **kwargs)))
    results = await asyncio.wait(tasks)
    total = sum([r.result() for r in results[0]])
    print(f"Total throughput: {total:.1f}/sec")

