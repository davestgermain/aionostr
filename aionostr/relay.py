import asyncio
import secrets
import time
import sys
import logging
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
    def __init__(self, url, verbose=False, origin:str = '', private_key:str='', connect_timeout: float=2.0, log=None):
        self.log = log or logging.getLogger(__name__)
        self.url = url
        self.ws = None
        self.receive_task = None
        self.subscriptions = defaultdict(lambda: Subscription(filters=[], queue=asyncio.Queue()))
        self.event_adds = asyncio.Queue()
        self.notices = asyncio.Queue()
        self.private_key = private_key
        self.origin = origin or url
        self.connected = False
        self.connect_timeout = connect_timeout

    async def connect(self, retries=5):
        for i in range(retries):
            try:
                async with timeout(self.connect_timeout):
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
        self.connected = True
        self.log.info("Connected to %s", self.url)

    async def reconnect(self):
        await self.connect(20)
        for sub_id, sub in self.subscriptions.items():
            self.log.debug("resubscribing to %s", sub.filters)
            await self.send(["REQ", sub_id, *sub.filters])

    async def close(self):
        if self.receive_task:
            self.receive_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False

    async def _receive_messages(self):
        while True:
            try:
                async with timeout(30.0):
                    message = await self.ws.recv()

                self.log.debug(message)
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
                    await self.authenticate(message[1])
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

    async def authenticate(self, challenge:str):
        if not self.private_key:
            import warnings
            warnings.warn("private key required to authenticate")
            return
        from .key import PrivateKey
        pk = PrivateKey(bytes.fromhex(self.private_key))
        auth_event = Event(
            kind=22242,
            pubkey=pk.public_key.hex(),
            tags=[
                ['challenge', challenge],
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
    def __init__(self, relays=None, verbose=False, origin='aionostr', private_key=None, log=None):
        self.log = log or logging.getLogger(__name__)
        self.relays = [Relay(r, origin=origin, private_key=private_key, log=log) for r in (relays or [])]
        self.subscriptions = {}
        self.connected = False
        self._connectlock = asyncio.Lock()

    @property
    def private_key(self):
        return None

    @private_key.setter
    def private_key(self, pk):
        for relay in self.relays:
            relay.private_key = pk

    def add(self, url, **kwargs):
        self.relays.append(Relay(url, **kwargs))

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
            results.append(asyncio.create_task(getattr(relay, func)(*args, **kwargs)))

        self.log.debug("Waiting for %s", func)
        return await asyncio.wait(results)

    async def connect(self):
        async with self._connectlock:
            if not self.connected:
                await self.broadcast('connect')
                self.connected = True
                tried = len(self.relays)
                connected = [relay for relay in self.relays if relay.connected]
                success = len(connected)
                self.relays = connected
                self.log.debug("Connected to %d out of %d relays", success, tried)

    async def close(self):
        await self.broadcast('close')

    async def add_event(self, event, check_response=False):
        await self.broadcast('add_event', event, check_response=check_response)

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


