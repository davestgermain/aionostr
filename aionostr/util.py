from nostr.key import PublicKey, PrivateKey
from . import bech32


def from_nip19(nip19string: str):
    """
    Decode nip-19 formatted string into:
    private key, public key, event id or profile public key
    """
    hrp, data, spec = bech32.bech32_decode(nip19string)
    data = bech32.convertbits(data, 5, 8)
    if hrp == 'npub':
        return PublicKey(bytes(data[:-1]))
    elif hrp == 'nsec':
        return PrivateKey(bytes(data[:-1]))
    elif hrp in ('nevent', 'nprofile', 'nrelay'):
        tlv = {0: [], 1: []}
        while data:
            t = data[0]
            try:
                l = data[1]
            except IndexError:
                break
            v = data[2:2+l]
            data = data[2+l:]
            if not v:
                continue
            tlv[t].append(v)
        if tlv[0]:
            if hrp != 'nrelay':
                key_or_id = bytes(tlv[0][0]).hex()
            else:
                key_or_id = bytes(tlv[0][0]).decode()
        else:
            key_or_id = ''
        relays = []
        for relay in tlv[1]:
            relays.append(bytes(relay).decode('utf8'))
        return hrp, key_or_id, relays


def to_nip19(ntype: str, payload: str, relays=None):
    """
    Encode object as nip-19 compatible string
    """
    if ntype in ('npub', 'nsec'):
        data = bytes.fromhex(payload)
    elif ntype in ('nprofile', 'nevent', 'nrelay'):
        data = bytearray()
        if ntype == 'nrelay':
            # payload is the relay url
            encoded = payload.encode()
            data.append(0)
            data.append(len(encoded))
            data.extend(encoded)
        else:
            # payload is event id
            event_id = bytes.fromhex(payload)
            data.append(0)
            data.append(len(event_id))
            data.extend(event_id)
            if relays:
                for r in relays:
                    r = r.encode()
                    data.append(1)
                    data.append(len(r))
                    data.extend(r)
    else:
        data = payload.encode()
    converted_bits = bech32.convertbits(data, 8, 5)
    return bech32.bech32_encode(ntype, converted_bits, bech32.Encoding.BECH32)
