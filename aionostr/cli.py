"""Console script for aionostr."""
import sys
import click
import asyncio
import time
from functools import wraps
from aionostr.aionostr import RelayManager, get_anything, add_event


DEFAULT_RELAYS = ['wss://brb.io', 'wss://relay.damus.io']


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
@click.argument("query")
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
@click.option('-s', '--stream', help='stream results', is_flag=True, default=False)
@async_cmd
async def query(query, relays, stream):
    """
    Run a query once and print events
    """
    import json
    query = json.loads(query)
    async with RelayManager(relays) as man:
        try:
            async for event in man.get_events(query, only_stored=not stream):
                print(event)
        except KeyboardInterrupt:
            return 0


@main.command()
@click.argument("anyid")
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
@click.option('-v', '--verbose', help='verbose results', is_flag=True, default=False)
@async_cmd
async def get(anyid, relays, verbose):
    """
    Get any nostr event
    """
    response = await get_anything(anyid, relays, verbose=verbose)
    if isinstance(response, list):
        for obj in response:
            click.echo(obj)
    else:
        click.echo(obj)


@main.command()
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
@click.option('-v', '--verbose', help='verbose results', is_flag=True, default=False)
@click.option('--content', default='', help='content')
@click.option('--kind', default=1, help='kind')
@click.option('--created_at', default=int(time.time()), help='created_at')
@click.option('--pubkey', default='', help='pubkey')
@click.option('--tags', default='[]', help='tags')
@async_cmd
async def send(content, kind, created_at, tags, pubkey, relays, verbose):
    import json, os
    from .util import to_nip19
    tags = json.loads(tags)
    private_key = os.getenv('NOSTR_KEY', '')
    if not sys.stdin.isatty():
        event = json.loads(sys.stdin.readline())
    else:
        event = None
    event_id = await add_event(
        relays,
        event=event,
        pubkey=pubkey,
        private_key=private_key,
        created_at=created_at,
        kind=kind,
        content=content,
        tags=tags,
    )
    click.echo(event_id)
    click.echo(to_nip19('nevent', event_id, relays))


@main.command()
@click.argument("ntype")
@click.argument("event_id")
@click.option('-r', 'relays', help='relay url', multiple=True, default=DEFAULT_RELAYS)
def make_nip19(ntype, event_id, relays):
    """
    """
    from .util import to_nip19
    obj = to_nip19(ntype, event_id, relays=relays)
    click.echo(obj)


@main.command()
def gen():
    from nostr.key import PrivateKey
    from .util import to_nip19

    pk = PrivateKey()
    click.echo(to_nip19('nsec', pk.hex()))
    click.echo(to_nip19('npub', pk.public_key.hex()))


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
