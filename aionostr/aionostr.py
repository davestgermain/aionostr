import asyncio
import secrets
import time
import sys
from collections import defaultdict
from websockets import connect
from .event import Event
try:
    from rapidjson import dumps, loads
except ImportError:
    from json import dumps, loads


class Relay:
    """
    Interact with a relay
    """
    def __init__(self, url, verbose=False):
        self.url = url
        self.ws = None
        self.receive_task = None
        self.subscriptions = defaultdict(asyncio.Queue)
        self.event_adds = asyncio.Queue()
        self.notices = asyncio.Queue()
        self.challenge = None
        self.verbose = verbose

    async def connect(self):
        self.ws = await connect(self.url, origin=self.url)
        self.receive_task = asyncio.create_task(self._receive_messages())
        await asyncio.sleep(0.01)

    async def close(self):
        self.receive_task.cancel()
        await self.ws.close()

    async def _receive_messages(self):
        while True:
            try:
                message = await self.ws.recv()
                if self.verbose:
                    sys.stderr.write(message + '\n')
                message = loads(message)
                if message[0] == 'EVENT':
                    await self.subscriptions[message[1]].put(Event(**message[2]))
                elif message[0] == 'EOSE':
                    await self.subscriptions[message[1]].put(None)
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

    async def send(self, message):
        await self.ws.send(dumps(message))

    async def add_event(self, event, check_response=False):
        if isinstance(event, Event):
            event = event.to_json_object()
        await self.send(["EVENT", event])
        if check_response:
            response = await self.event_adds.get()
            return response[1]

    async def subscribe(self, sub_id: str, *filters, queue=None):
        if queue is not None:
            self.subscriptions[sub_id] = queue
        await self.send(["REQ", sub_id, *filters])
        return self.subscriptions[sub_id]

    async def unsubscribe(self, sub_id):
        await self.send(["CLOSE", sub_id])
        del self.subscriptions[sub_id]

    async def authenticate(self, private_key:str):
        if not self.challenge:
            return False
        from nostr.key import PrivateKey
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
    def __init__(self, relays=None, verbose=False):
        self.relays = [Relay(r, verbose=verbose) for r in (relays or [])]
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

    async def add_event(self, event):
        await self.broadcast('add_event', event)

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


async def get_anything(anything:str, relays=None, verbose=False, only_stored=True):
    """
    Return anything from the nostr network
    anything: event id, nprofile, nevent, npub, nsec, or query
    """
    from .util import from_nip19
    query = None
    single_event = False
    if isinstance(anything, list):
        if anything[0] == 'REQ':
            query = anything[2]
        else:
            raise NotImplementedError(anything)
    elif isinstance(anything, dict):
        query = anything
    elif anything.strip().startswith('{'):
        query = loads(anything)
    elif anything.startswith(('nprofile', 'nevent', 'npub', 'nsec')):
        obj = from_nip19(anything)
        if not isinstance(obj, tuple):
            yield obj.hex()
        else:
            relays = obj[2] or relays
            if obj[0] == 'nprofile':
                query = {"kinds": [0], "authors": [obj[1]]}
            else:
                query = {"ids": [obj[1]]}
                single_event = True
    else:
        query = {"ids": [anything]}
        single_event = True
    if verbose:
        import sys
        sys.stderr.write(f"Retrieving {query} from {relays}\n")
    if query:
        if not relays:
            raise NotImplementedError("No relays to use")
        async with Manager(relays, verbose=verbose) as man:
            async for event in man.get_events(query, single_event=single_event, only_stored=only_stored):
                yield event


async def add_event(relays, event:dict=None, private_key='', kind=1, pubkey='', content='', created_at=None, tags=None, verbose=False):
    """
    Add an event to the network, using the given relays
    event can be specified (as a dict)
    or will be created from the passed in parameters
    """
    if not event:
        created_at = created_at or int(time.time())
        tags = tags or []
        from nostr.key import PrivateKey
        if not private_key:
            raise Exception("Missing private key")

        if private_key.startswith('nsec'):
            from .util import from_nip19
            private_key = from_nip19(private_key).hex()
        prikey = PrivateKey(bytes.fromhex(private_key))

        if not pubkey:
            pubkey = prikey.public_key.hex()
        event = Event(pubkey=pubkey, content=content, created_at=created_at, tags=tags, kind=kind)
        event.sign(prikey.hex())
        event_id = event.id
    else:
        event_id = event['id']
    async with Manager(relays, verbose=verbose) as man:
        if private_key:
            await man.authenticate(private_key)
        await man.add_event(event)
    return event_id


async def add_events(relays, event_iterator):
    async with Manager(relays) as man:
        for event in event_iterator:
            await man.add_event(event)
