=====
Usage
=====

To use aionostr in a project::

    import aionostr

The high-level API looks like this::

    event = await aionostr.get_anything('nprofile1qqsv0knzz56gtm8mrdjhjtreecl7dl8xa47caafkevfp67svwvhf9hcpz3mhxue69uhkgetnvd5x7mmvd9hxwtn4wvspak3h')
    events = await aionostr.get_anything({"kinds": [1], "limit":10}, relays=['wss://brb.io', 'wss://nostr.mom'])

    await aionostr.add_event(['wss://brb.io', 'wss://nostr.mom'], kind=20000, content='test', private_key=private_key)

To use aionostr on the command line::
    aionostr get nprofile1qqsv0knzz56gtm8mrdjhjtreecl7dl8xa47caafkevfp67svwvhf9hcpz3mhxue69uhkgetnvd5x7mmvd9hxwtn4wvspak3h
    aionostr get -v nevent1qqsxpnzhw2ddf2uplsxgc5ctr9h6t65qaalzvzf0hvljwrz8q64637spp3mhxue69uhkyunz9e5k75j6gxm
    aionostr get '{"kinds": [1], "limit":10}'
    aionostr send --kind 1 --content test --private-key <privatekey>

