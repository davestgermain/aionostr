"""Top-level package for aionostr."""

__author__ = """Dave St.Germain"""
__email__ = 'dave@st.germa.in'
__version__ = '0.2.0'

import time
from .relay import Manager, Relay


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
        from .event import Event
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