========
aionostr
========


.. image:: https://img.shields.io/pypi/v/aionostr.svg
        :target: https://pypi.python.org/pypi/aionostr

.. .. image:: https://img.shields.io/travis/davestgermain/aionostr.svg
..         :target: https://travis-ci.com/davestgermain/aionostr

.. .. image:: https://readthedocs.org/projects/aionostr/badge/?version=latest
..         :target: https://aionostr.readthedocs.io/en/latest/?version=latest
..         :alt: Documentation Status




asyncio nostr client


* Free software: BSD license
* Documentation: https://aionostr.readthedocs.io.


Features
--------

* Retrieve anything from the nostr network, using one command:

.. code-block:: console

        $ aionostr get nprofile1qqsv0knzz56gtm8mrdjhjtreecl7dl8xa47caafkevfp67svwvhf9hcpz3mhxue69uhkgetnvd5x7mmvd9hxwtn4wvspak3h
        $ aionostr get -v nevent1qqsxpnzhw2ddf2uplsxgc5ctr9h6t65qaalzvzf0hvljwrz8q64637spp3mhxue69uhkyunz9e5k75j6gxm
        $ aionostr query -s -q '{"kinds": [1], "limit":10}'
        $ aionostr send --kind 1 --content test --private-key <privatekey>
        $ aionostr mirror -r wss://source.relay -t wss://target.relay --verbose '{"kinds": [4]}'

Set environment variables:

.. code-block:: console

        NOSTR_RELAYS=wss://brb.io,wss://nostr.mom
        NOSTR_KEY=`aionostr gen | head -1`


Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
