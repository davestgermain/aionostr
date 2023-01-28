import asyncio
import secrets
import time
import sys
from contextlib import asynccontextmanager
from collections import defaultdict, namedtuple
from websockets import connect, exceptions
from .event import Event

try:
    from rapidjson import dumps, loads
except ImportError:
    from json import dumps, loads

if hasattr(asyncio, 'timeout'):
    timeout = asyncio.timeout
else:
    # python < 3.11 does not have asyncio.timeout
    # rather than re-implement it, we'll just do nothing
    @asynccontextmanager
    async def timeout(duration):
        yield


Subscription = namedtuple('Subscription', ['filters','queue'])


class Relay:
    """
    Interact with a relay
    """
    def __init__(self, url, verbose=False, origin:str = ''):
        self.url = url
        self.ws = None
        self.receive_task = None
        self.subscriptions = defaultdict(lambda: Subscription(filters=[], queue=asyncio.Queue()))
        self.event_adds = asyncio.Queue()
        self.notices = asyncio.Queue()
        self.challenge = None
        self.verbose = verbose
        self.origin = origin or url

    async def connect(self, retries=5):
        for i in range(retries):
            try:
                self.ws = await connect(self.url, origin=self.origin)
            except:
                await asyncio.sleep(0.2 * i)
            else:
                break
        else:
            raise Exception(f"Cannot connect to {self.url}")
        if self.receive_task is None:
            self.receive_task = asyncio.create_task(self._receive_messages())
        await asyncio.sleep(0.01)

    async def reconnect(self):
        await self.connect(20)
        for sub_id, sub in self.subscriptions.items():
            if self.verbose:
                sys.stderr.write(f'resubscribing to {sub.filters}')
            await self.send(["REQ", sub_id, *sub.filters])

    async def close(self):
        self.receive_task.cancel()
        await self.ws.close()

    async def _receive_messages(self):
        while True:
            try:
                async with timeout(30.0):
                    message = await self.ws.recv()

                if self.verbose:
                    sys.stderr.write(message + '\n')
                message = loads(message)
                if message[0] == 'EVENT':
                    await self.subscriptions[message[1]].queue.put(Event(**message[2]))
                elif message[0] == 'EOSE':
                    await self.subscriptions[message[1]].queue.put(None)
                elif message[0] == 'OK':
                    await self.event_adds.put(message)
                elif message[0] == 'NOTICE':
                    await self.notices.put(message[1])
                elif message[0] == 'AUTH':
                    self.challenge = message[1]
                else:
                    sys.stderr.write(message)
            except asyncio.CancelledError:
                return
            except exceptions.ConnectionClosedError:
                await self.reconnect()
            except asyncio.TimeoutError:
                continue
            except:
                import traceback; traceback.print_exc()

    async def send(self, message):
        try:
            await self.ws.send(dumps(message))
        except exceptions.ConnectionClosedError:
            await self.reconnect()
            await self.ws.send(dumps(message))

    async def add_event(self, event, check_response=False):
        if isinstance(event, Event):
            event = event.to_json_object()
        await self.send(["EVENT", event])
        if check_response:
            response = await self.event_adds.get()
            return response[1]

    async def subscribe(self, sub_id: str, *filters, queue=None):
        self.subscriptions[sub_id] = Subscription(filters=filters, queue=queue or asyncio.Queue())
        await self.send(["REQ", sub_id, *filters])
        return self.subscriptions[sub_id].queue

    async def unsubscribe(self, sub_id):
        await self.send(["CLOSE", sub_id])
        del self.subscriptions[sub_id]

    async def authenticate(self, private_key:str):
        if not self.challenge:
            return False
        from .key import PrivateKey
        pk = PrivateKey(bytes.fromhex(private_key))
        auth_event = Event(
            kind=22242,
            pubkey=pk.public_key.hex(),
            tags=[
                ['challenge', self.challenge],
                ['relay', self.url]
            ]
        )
        auth_event.sign(pk.hex())
        await self.send(["AUTH", auth_event.to_json_object()])
        await asyncio.sleep(0.1)
        return True

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, ex_type, ex, tb):
        await self.close()


class Manager:
    """
    Manage a collection of relays
    """
    def __init__(self, relays=None, verbose=False, origin='aionostr'):
        self.relays = [Relay(r, verbose=verbose, origin=origin) for r in (relays or [])]
        self.subscriptions = {}

    def add(self, url):
        self.relays.append(Relay(url))

    async def monitor_queues(self, queues, output):
        seen = set()
        num = len(queues)
        num_eose = 0
        while True:
            get_funcs = [queue.get() for queue in queues]
            for func in asyncio.as_completed(get_funcs):
                result = await func
                if result:
                    eid = result.id_bytes
                    if eid not in seen:
                        await output.put(result)
                        seen.add(eid)
                else:
                    num_eose += 1
                    if num_eose == num:
                        await output.put(result)

    async def broadcast(self, func, *args, **kwargs):
        results = []
        for relay in self.relays:
            results.append(await getattr(relay, func)(*args, **kwargs))
        return results

    async def connect(self):
        await self.broadcast('connect')

    async def close(self):
        await self.broadcast('close')

    async def add_event(self, event, check_response=False):
        await self.broadcast('add_event', event, check_response=check_response)

    async def authenticate(self, private_key:str):
        await self.broadcast('authenticate', private_key)

    async def subscribe(self, sub_id: str, *filters):
        queues = []
        for relay in self.relays:
            queues.append(await relay.subscribe(sub_id, *filters))
        queue = asyncio.Queue()
        self.subscriptions[sub_id] = asyncio.create_task(self.monitor_queues(queues, queue))
        return queue

    async def unsubscribe(self, sub_id):
        await self.broadcast('unsubscribe', sub_id)
        self.subscriptions[sub_id].cancel()
        del self.subscriptions[sub_id]

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, ex_type, ex, tb):
        await self.close()

    async def get_events(self, *filters, only_stored=True, single_event=False):
        sub_id = secrets.token_hex(4)
        queue = await self.subscribe(sub_id, *filters)
        while True:
            event = await queue.get()
            if event is None:
                if only_stored:
                    break
            else:
                yield event
                if single_event:
                    break
        await self.unsubscribe(sub_id)


