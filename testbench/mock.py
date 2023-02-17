import socketserver
import threading
import ipaddress
import queue
import sys
import select
import socket
import logging

try:
    from .packet import Packet, ControlPacket, DataPacket, NTPPacket
except (ImportError, ModuleNotFoundError):
    from packet import Packet, ControlPacket, DataPacket, NTPPacket

log = logging.getLogger(__name__)

class MockServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue.Queue()
        self.resp_q = queue.Queue()
        self.send_response = False
        self.ip = "127.0.0.1"


    def handle_error(self, request, client_address):
        self.queue.put(sys.exc_info())

    def await_packet(self, packet_type, timeout):
        try:
            packet = self.queue.get(timeout=timeout)
            if isinstance(packet, tuple):
                # This is an error
                err_type, value, tr = packet
                raise AssertionError(
                    'Did not receive expected packet due to previous errors!') from value

            elif isinstance(packet, packet_type):
                return packet
            else:
                ValueError(
                    f'MockServer received unexpected packet type. Expected {packet_type} Got: {type(packet)}')
        except queue.Empty:
            return None


class MockServerUDP(socketserver.ThreadingMixIn, socketserver.UDPServer):
    allow_reuse_address = True
    response_timeout = 2.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue.Queue()
        self.resp_q = queue.Queue()
        self.send_response = False

        self.ip = "127.0.0.1"

    def handle_error(self, request, client_address):
        self.queue.put(sys.exc_info())

    def await_packet(self, packet_type, timeout):
        try:
            packet = self.queue.get(timeout=timeout)
            if isinstance(packet, tuple):
                # This is an error
                err_type, value, tr = packet
                raise AssertionError(
                    'Did not receive expected packet due to previous errors!') from value

            elif isinstance(packet, packet_type):
                return packet
            else:
                ValueError(
                    f'MockServer received unexpected packet type. Expected {packet_type} Got: {type(packet)}')
        except queue.Empty:
            return None


class MockClient:
    def __init__(self, req: Packet, ip=None, port=1400):
        self.running = False
        self.queue = queue.Queue()
        self.packet = req
        self.ip = ip
        self.port = port
        self.executing_thread = None

        self.clientConnected = threading.Event()


    def stop(self):
        self.running = False
        self.executing_thread.join()

    def await_packet(self, timeout):
        try:
            packet = self.queue.get(timeout=timeout)
            if isinstance(packet, tuple):
                # This is an error
                err_type, value, tr = packet
                raise AssertionError(
                    'Did not receive expected packet due to previous errors!') from value
            elif isinstance(packet, DataPacket):
                return packet
            elif isinstance(packet, ControlPacket):
                return packet
            else:
                ValueError(
                    f'MockClient received unexpected packet type. Expected DataPacket/CtrlPacket Got: {type(packet)}')
        except queue.Empty:
            return None

    def run(self):
        self.running = True
        self.executing_thread = threading.current_thread()
        sock = socket.socket(type=socket.SOCK_STREAM)
        reply = b''

        try:
            if not self.ip:
                self.ip = "127.0.0.1"

            sock.settimeout(3.0)

            sock.connect((self.ip, self.port))
            self.clientConnected.set()

            sock.sendall(self.packet.serialize())

            # No response expected for lookup/reply messages
            if isinstance(self.packet, ControlPacket) and self.packet.method in ['LOOKUP', 'REPLY', 'JOIN']:
                sock.close()
                return

            while self.running:
                readable, _, _ = select.select([sock], [], [], 1.0)

                if not sock in readable:
                    break

                data = sock.recv(1000)

                if not data:
                    break

                reply += data
            try:
                # Packet response type depends on sent message
                response = self.packet.__class__.parse(reply)
                self.queue.put(response)
            except ValueError:
                self.queue.put(sys.exc_info())

        except IOError as e:
            pass
        finally:
            sock.close()


class GeneralPktHandler(socketserver.StreamRequestHandler):
    def send_response(self):
        try:
            packet = self.server.resp_q.get(timeout=2.0)
            if isinstance(packet, Packet):
                buffer = packet.serialize()
                self.wfile.write(buffer)
            else:
                p, host, port = packet
                self._connect_and_send(p, host, port)

        except queue.Empty:
            raise RuntimeError(
                'Expected response packet in queue! This should not happen!')

    @staticmethod
    def _connect_and_send(p, host, port):
        log = logging.getLogger(__name__)
        sock = socket.socket(type=socket.SOCK_STREAM)
        try:
            log.debug(f"Sending to {host}:{port}")
            sock.settimeout(3.0)
            sock.connect((host, port))
            sock.sendall(p.serialize())
            log.debug('Sent successfully')
        except Exception as e:
            log.error(e)
        finally:
            sock.close()

    def handle_ctrl_packet(self, data):
        while len(data) < 11:
            readable, _, _ = select.select([self.rfile], [], [], 3.0)
            if self.rfile in readable:
                chunk = self.rfile.read1(11)
                if not chunk:
                    break
                data += chunk
            else:
                raise ValueError("Peer did not send full Control packet")

            packet = ControlPacket.parse(data)
            self.server.queue.put(packet)

    def handle_data_packet(self, data):
        while len(data) < 7:
            readable, _, _ = select.select([self.rfile], [], [], 3.0)
            if self.rfile in readable:
                chunk = self.rfile.read1(7)
                if not chunk:
                    break
                data += chunk
            else:
                break

        if len(data) < 7:
            raise ValueError(
                'Peer did not send enough bytes to parse a data/client packet header')

        key_len, value_len = DataPacket.len_from_header(data)

        while len(data) < 7 + key_len + value_len:
            readable, _, _ = select.select([self.rfile], [], [], 3.0)
            if self.rfile in readable:
                chunk = self.rfile.read1(1)
                if not chunk:
                    break
                data += chunk
            else:
                break

        packet = DataPacket.parse(data)
        self.server.queue.put(packet)

    def get_first_byte(self):
        data = b''
        readable, _, _ = select.select([self.rfile], [], [], 3.0)

        if self.rfile not in readable:
            raise ValueError(
                "Peer did not send a single byte to determine packet type!")

        data += self.rfile.read1(1)
        if len(data) == 0:
            raise ValueError(
                "Peer did not send a single byte to determine packet type!")

        return data

    def handle(self):
        data = self.get_first_byte()
        if Packet.packet_type(data) == ControlPacket:
            self.handle_ctrl_packet(data)
        else:
            self.handle_data_packet(data)

        if self.server.send_response:
            time.sleep(0.1)
            self.send_response()


class ControlPktHandler(GeneralPktHandler):
    def handle(self):
        data = self.get_first_byte()
        if not Packet.packet_type(data) == ControlPacket:
            raise ValueError(
                'Expected control packet but control bit is not set!')

        self.handle_ctrl_packet(data)
        if self.server.send_response:
            self.send_response()


class DataPktHandler(GeneralPktHandler):
    def handle(self):
        data = self.get_first_byte()
        if not Packet.packet_type(data) == DataPacket:
            raise ValueError(
                'Expected data/client packet but control bit is set!')

        self.handle_data_packet(data)
        if self.server.send_response:
            self.send_response()


class NTPPktHandler(socketserver.DatagramRequestHandler):
    def handle(self):
        packet = NTPPacket.parse(self.packet)
        self.server.queue.put(packet)

        if self.server.send_response:
            self.send_response()

    def send_response(self):
        try:
            if self.server.response_timeout is not None:
                packet = self.server.resp_q.get(
                    timeout=self.server.response_timeout)
            else:
                packet = self.server.resp_q.get()

            if isinstance(packet, Packet):
                buffer = packet.serialize()
                self.socket.sendto(buffer, self.client_address)
            else:
                p, host, port = packet
                GeneralPktHandler.connect_and_send(p, host, port)

        except queue.Empty:
            raise RuntimeError(
                'Expected response packet in queue! This should not happen!')
