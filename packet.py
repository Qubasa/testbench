import ipaddress

import datetime


class Packet:
    @classmethod
    def parse(cls, buffer):
        raise NotImplementedError()

    def serialize(self):
        raise NotImplementedError()

    @staticmethod
    def packet_type(buffer):
        if len(buffer) == 0:
            raise ValueError('Unable to determine packet type of empty buffer!')

        if ((buffer[0] & (1 << 7)) >> 7) == 1:
            return ControlPacket
        else:
            return DataPacket


class NullPacket(Packet):
    def serialize(self):
        return b''


class DataPacket(Packet):
    def __init__(self, method, key=b'', value=b'', ack=False):
        self.method = method
        self.key = key
        self.value = value
        self.ack = ack

    @classmethod
    def len_from_header(cls, buffer):
        if len(buffer) < 7:
            raise ValueError(f'Header too short! Expected 7 bytes but got only {len(buffer)}!')

        if (buffer[0] & (1 << 7)) >> 7:
            raise ValueError('Expected data/client packet but got control packet instead!')

        key_len = (buffer[1] << 8) | \
                  (buffer[2] << 0)
        value_len = (buffer[3] << 24) | \
                    (buffer[4] << 16) | \
                    (buffer[5] << 8) | \
                    (buffer[6] << 0)

        return key_len, value_len

    @classmethod
    def parse(cls, buffer):
        key_len, value_len = cls.len_from_header(buffer)
        if len(buffer) < 7 + key_len + value_len:
            raise ValueError('Received Packet too short!')

        if key_len > 0:
            key = buffer[7:7 + key_len]
        else:
            key = b''

        if value_len > 0:
            value = buffer[7 + key_len:7 + key_len + value_len]
        else:
            value = b''

        del_set = (buffer[0] & (1 << 0)) >> 0
        set_set = (buffer[0] & (1 << 1)) >> 1
        get_set = (buffer[0] & (1 << 2)) >> 2
        ack_set = (buffer[0] & (1 << 3)) >> 3

        if del_set == 1:
            method = 'DELETE'
            if (get_set == 1) or (set_set == 1):
                raise ValueError('Conflicting Flag bits set!')

        elif set_set == 1:
            method = 'SET'

            if (get_set == 1) or (del_set == 1):
                raise ValueError('Conflicting Flag bits set!')

        elif get_set == 1:
            method = 'GET'
            if (del_set == 1) or (set_set == 1):
                raise ValueError('Conflicting Flag bits set!')

        else:
            raise ValueError('No method set in Flag bits!')

        return cls(method=method, key=key, value=value, ack=(ack_set == 1))

    def serialize(self):
        p = bytearray(7 + len(self.key) + len(self.value))
        if self.method == 'GET':
            p[0] |= 1 << 2
        elif self.method == 'SET':
            p[0] |= 1 << 1
        elif self.method == 'DELETE':
            p[0] |= 1 << 0
        else:
            raise RuntimeError('This should not happen! Probably a typo!')

        if self.ack:
            p[0] |= 1 << 3

        key_len = len(self.key)
        value_len = len(self.value)
        p[1] = (key_len >> 8) & 0xFF
        p[2] = (key_len >> 0) & 0xFF

        p[3] = (value_len >> 24) & 0xFF
        p[4] = (value_len >> 16) & 0xFF
        p[5] = (value_len >> 8) & 0xFF
        p[6] = (value_len >> 0) & 0xFF

        if key_len > 0:
            p[7:7 + key_len] = self.key
        if value_len > 0:
            p[7 + key_len:7 + key_len + value_len] = self.value

        return p


class ControlPacket(Packet):
    def __init__(self, method: str, hash_id: int, node_id: int, node_ip: ipaddress.IPv4Address, node_port: int):
        self.hash_id = hash_id
        self.node_id = node_id
        self.ip = node_ip
        self.port = node_port
        self.method = method

        self.raw = None

    def serialize(self):
        p = bytearray(11)
        p[0] |= 1 << 7

        if self.method == 'REPLY':
            p[0] |= 1 << 1
        elif self.method == 'LOOKUP':
            p[0] |= 1 << 0
        elif self.method == 'STABILIZE':
            p[0] |= 1 << 2
        elif self.method == 'NOTIFY':
            p[0] |= 1 << 3
        elif self.method == 'JOIN':
            p[0] |= 1 << 4
        elif self.method == 'FACK':
            p[0] |= 1 << 5
        elif self.method == 'FINGER':
            p[0] |= 1 << 6
        else:
            raise RuntimeError('Unrecognized method for control packet! Cannot serialize!')

        p[1] = (self.hash_id >> 8) & 0xFF
        p[2] = (self.hash_id >> 0) & 0xFF

        p[3] = (self.node_id >> 8) & 0xFF
        p[4] = (self.node_id >> 0) & 0xFF

        p[5:9] = self.ip.packed  # MSB first

        p[9] = (self.port >> 8) & 0xFF
        p[10] = (self.port >> 0) & 0xFF

        return p

    @classmethod
    def parse(cls, buffer):
        if len(buffer) < 11:
            raise ValueError('Not enough data to parse Control packet!')

        if not buffer[0] & (1 << 7):
            raise ValueError('Control bit not set! Expected control packet to parse!')

        if buffer[0] & (1 << 1):
            method = 'REPLY'
        elif buffer[0] & (1 << 0):
            method = 'LOOKUP'
        elif buffer[0] & (1 << 2):
            method = 'STABILIZE'
        elif buffer[0] & (1 << 3):
            method = 'NOTIFY'
        elif buffer[0] & (1 << 4):
            method = 'JOIN'
        elif buffer[0] & (1 << 5):
            method = 'FACK'
        elif buffer[0] & (1 << 6):
            method = 'FINGER'
        else:
            raise ValueError('No method bit set in Control packet!')

        hash_id = (buffer[1] << 8) | (buffer[2] << 0)
        node_id = (buffer[3] << 8) | (buffer[4] << 0)
        node_ip = ipaddress.IPv4Address(buffer[5:9])
        node_port = (buffer[9] << 8) | (buffer[10] << 0)

        p = cls(method, hash_id, node_id, node_ip, node_port)
        p.raw = buffer
        return p


class NTPShort:
    def __init__(self, seconds: int, fraction: int):
        self.seconds = seconds
        self.fraction = fraction

    def to_bytes(self):
        b = bytearray(4)
        b[0:2] = self.seconds.to_bytes(2, 'big', signed=False)
        b[2:4] = self.fraction.to_bytes(2, 'big', signed=False)
        return b

    def __eq__(self, other):
        if not isinstance(other, NTPShort):
            return False

        return self.seconds == other.seconds and self.fraction == other.fraction

    def __ne__(self, other):
        return not self.__eq__(other)


class NTPTimestamp:
    UNIX_EPOCH_OFFSET = 2208988800

    def __init__(self, seconds: int, fraction: int):
        self.seconds = seconds
        self.fraction = fraction

    def to_bytes(self):
        b = bytearray(8)
        b[0:4] = self.seconds.to_bytes(4, 'big', signed=False)
        b[4:8] = self.fraction.to_bytes(4, 'big', signed=False)
        return b

    def to_timestamp(self) -> float:
        ts = 0.0
        ts += self.seconds - self.UNIX_EPOCH_OFFSET
        ts += float(self.fraction) / float(2 ** 32)
        return ts

    @classmethod
    def from_timestamp(cls, ts):
        secs = int(ts) + cls.UNIX_EPOCH_OFFSET
        fracs = int((ts - int(ts)) * 2 ** 32)
        return cls(secs, fracs)

    def __repr__(self):
        return f'NTPTimestamp {self.to_timestamp()}'

    def __eq__(self, other):
        if not isinstance(other, NTPTimestamp):
            return False

        return self.seconds == other.seconds and self.fraction == other.fraction

    def __ne__(self, other):
        return not self.__eq__(other)


class NTPPacket(Packet):
    MODE_CLIENT = 3
    MODE_SERVER = 4

    def __init__(self, li: int, version: int, mode: int, stratum: int, poll: int, precision: int,
                 root_delay: NTPShort, root_dispersion: NTPShort,
                 reference_id: bytes,
                 reference_ts: NTPTimestamp,
                 origin_ts: NTPTimestamp,
                 recv_ts: NTPTimestamp,
                 transmit_ts: NTPTimestamp):
        self.li = li
        self.version = version
        self.mode = mode
        self.stratum = stratum
        self.poll = poll
        self.precision = precision
        self.root_delay = root_delay
        self.root_dispersion = root_dispersion
        self.reference_id = reference_id
        self.reference_ts = reference_ts
        self.origin_ts = origin_ts
        self.recv_ts = recv_ts
        self.transmit_ts = transmit_ts

    @classmethod
    def parse(cls, buffer):
        if len(buffer) < 48:
            raise ValueError('Not enough data to parse NTP packet!')

        flags = buffer[0]
        li = (flags >> 6) & 0b11
        version = (flags >> 3) & 0b111
        mode = (flags >> 0) & 0b111

        stratum = buffer[1]
        poll = int.from_bytes(buffer[2:3], 'big', signed=True)
        precision = int.from_bytes(buffer[3:4], 'big', signed=True)

        root_delay = NTPShort(buffer[4] << 8 | buffer[5], buffer[6] << 8 | buffer[7])
        root_dispersion = NTPShort(buffer[8] << 8 | buffer[9], buffer[10] << 8 | buffer[11])
        reference_id = buffer[12:16]

        reference_ts = NTPTimestamp(int.from_bytes(buffer[16:20], 'big'),
                                    int.from_bytes(buffer[20:24], 'big'))

        origin_ts = NTPTimestamp(int.from_bytes(buffer[24:28], 'big'),
                                 int.from_bytes(buffer[28:32], 'big'))

        recv_ts = NTPTimestamp(int.from_bytes(buffer[32:36], 'big'),
                               int.from_bytes(buffer[36:40], 'big'))

        transmit_ts = NTPTimestamp(int.from_bytes(buffer[40:44], 'big'),
                                   int.from_bytes(buffer[44:48], 'big'))

        return cls(li, version, mode, stratum, poll, precision, root_delay, root_dispersion, reference_id,
                   reference_ts, origin_ts, recv_ts, transmit_ts)

    def serialize(self):
        buffer = bytearray(48)
        buffer[0] = (self.li & 0b11) << 6 | (self.version & 0b111) << 3 | (self.mode & 0b111) << 0
        buffer[1] = self.stratum
        buffer[2:3] = self.poll.to_bytes(1, 'big', signed=True)
        buffer[3:4] = self.precision.to_bytes(1, 'big', signed=True)
        buffer[4:8] = self.root_delay.to_bytes()
        buffer[8:12] = self.root_dispersion.to_bytes()
        buffer[12:16] = self.reference_id

        buffer[16:24] = self.reference_ts.to_bytes()
        buffer[24:32] = self.origin_ts.to_bytes()
        buffer[32:40] = self.recv_ts.to_bytes()
        buffer[40:48] = self.transmit_ts.to_bytes()

        assert len(buffer) == 48

        return buffer

    @classmethod
    def from_datetime(cls, dt: datetime.datetime, delta: datetime.timedelta, rdisp=None):
        li = 0
        version = 4
        mode = cls.MODE_SERVER
        stratum = 1
        poll = 0
        precision = 0
        root_delay = NTPShort(0, 0)
        root_dispersion = NTPShort(0, 0) if rdisp is None else rdisp
        reference_id = b'XCOM'
        reference_ts = NTPTimestamp(0, 0)
        origin_ts = NTPTimestamp(0, 0)

        recv_ts = NTPTimestamp.from_timestamp(dt.timestamp())
        transmit_ts = NTPTimestamp.from_timestamp((dt + delta).timestamp())

        return cls(li, version, mode, stratum, poll, precision, root_delay, root_dispersion, reference_id,
                   reference_ts, origin_ts, recv_ts, transmit_ts)
