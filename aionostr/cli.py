"""Console script for aionostr."""
import sys
import click
import asyncio
import time
import os
from functools import wraps
from . import get_anything, add_event

DEFAULT_RELAYS = os.getenv('NOSTR_RELAYS', 'wss://nostr-pub.wellorder.net,wss://brb.io,wss://relay.damus.io').split(',')


def async_cmd(func):
  @wraps(func)
  def wrapper(*args, **kwargs):
    return asyncio.run(func(*args, **kwargs))
  return wrapper


@click.group()
def main(args=None):
    """Console script for aionostr."""
    # click.echo("Replace this message by putting your code into "
    #            "aionostr.cli.main")
    # click.echo("See click documentation at https://click.palletsprojects.com/")
    return 0


@main.command()
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
@click.option('-s', '--stream', help='stream results', is_flag=True, default=False)
@click.option('-q', '--query', help='query json')
@click.option('--ids', help='ids')
@click.option('--authors', help='authors')
@click.option('--kinds', help='kinds')
@click.option('--etags', help='etags')
@click.option('--ptags', help='ptags')
@click.option('--since', help='since')
@click.option('--until', help='until')
@click.option('--limit', help='limit')
@async_cmd
async def query(ids, authors, kinds, etags, ptags, since, until, limit, query, relays, stream):
    """
    Run a query once and print events
    """
    import json
    if not sys.stdin.isatty():
        query = json.loads(sys.stdin.readline())
    elif query:
        query = json.loads(query)
    else:
        query = {}
        if ids:
            query['ids'] = ids.split(',')
        if authors:
            query['authors'] = authors.split(',')
        if kinds:
            query['kinds'] = [int(k) for k in kinds.split(',')]
        if etags:
            query['#e'] = etags.split(',')
        if ptags:
            query['#p'] = ptags.split(',')
        if since:
            query['since'] = int(since)
        if until:
            query['until'] = int(until)
        if limit:
            query['limit'] = int(limit)
    if not query:
        click.echo("some type of query is required")
        return -1
    async for obj in get_anything(query, relays, only_stored=not stream):
        click.echo(obj)



@main.command()
@click.argument("anything")
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
@click.option('-v', '--verbose', help='verbose results', is_flag=True, default=False)
@async_cmd
async def get(anything, relays, verbose, stream=False):
    """
    Get any nostr event
    """
    async for obj in get_anything(anything, relays, verbose=verbose, only_stored=not stream):
        click.echo(obj)


@main.command()
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
@click.option('-v', '--verbose', help='verbose results', is_flag=True, default=False)
@click.option('--content', default='', help='content')
@click.option('--kind', default=20000, help='kind', type=int)
@click.option('--created', default=int(time.time()), type=int, help='created_at')
@click.option('--pubkey', default='', help='public key')
@click.option('--tags', default='[]', help='tags')
@click.option('--private-key', default='', help='private key')
@async_cmd
async def send(content, kind, created, tags, pubkey, relays, private_key, verbose):
    """
    Send an event to the network

    private key can be set using environment variable NOSTR_KEY
    """
    import json
    from .util import to_nip19
    tags = json.loads(tags)
    private_key = private_key or os.getenv('NOSTR_KEY', '')
    if not sys.stdin.isatty():
        event = json.loads(sys.stdin.readline())
    else:
        event = None
    event_id = await add_event(
        relays,
        event=event,
        pubkey=pubkey,
        private_key=private_key,
        created_at=int(created),
        kind=kind,
        content=content,
        tags=tags,
        verbose=verbose,
    )
    click.echo(event_id)
    click.echo(to_nip19('nevent', event_id, relays))


@main.command()
@click.argument("ntype")
@click.argument("obj_id")
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
def make_nip19(ntype, obj_id, relays):
    """
    Create nip-19 string for given object id
    """
    from .util import to_nip19
    obj = to_nip19(ntype, obj_id, relays=relays)
    click.echo(obj)


@main.command()
def gen():
    """
    Generate a private/public key pair
    """
    from nostr.key import PrivateKey
    from .util import to_nip19

    pk = PrivateKey()
    click.echo(to_nip19('nsec', pk.hex()))
    click.echo(to_nip19('npub', pk.public_key.hex()))


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
