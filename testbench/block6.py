import queue
import ipaddress
import time
import pdb
import logging
import subprocess
import threading
import unittest
import typing
import sys
try:
    from .packet import DataPacket, ControlPacket, NullPacket, Packet
    from .mock import MockServer, MockClient, GeneralPktHandler, ControlPktHandler
except (ImportError, ModuleNotFoundError):
    from packet import DataPacket, ControlPacket, NullPacket, Packet
    from mock import MockServer, MockClient, GeneralPktHandler, ControlPktHandler


ASSIGNMENT = 'Abgabe Block 6'


class ExecAsyncHandler(threading.Thread):
    def __init__(self, cmd):
        self.cmd = cmd
        # calling parent class constructor
        threading.Thread.__init__(self)
        self.log = logging.getLogger(__name__)
        self.stdout = None
        self.stderr = None
        self.retcode = None

    def run(self, timeout=5):
        self.log.info(f"Thread executing cmd: {self.cmd}")
        process = subprocess.run(
            self.cmd, capture_output=True, timeout=timeout)
        self.stdout = process.stdout
        self.stderr = process.stderr
        self.retcode = process.returncode


    def collect(self):
        while self.is_alive():
            time.sleep(0.2)

        sys.stderr.write(self.stderr.decode("utf-8"))
        sys.stderr.write(self.stdout.decode("utf-8"))

        return self.retcode, self.stderr, self.stdout

def exec_async(cmd):
    handler = ExecAsyncHandler(cmd)
    handler.start()
    return handler


def collect_trace(handlers: [ExecAsyncHandler]):
    traces = []

    for i, h in enumerate(handlers):
        status, out, err = h.collect()
        traces.append(f'Stdout{i}: {out} // Stderr{i}: {err}')

    return ' '.join(traces)


def pseudo_hash(key: bytes):
    if len(key) >= 2:
        return int.from_bytes(key[0:2], 'big')
    elif len(key) == 0:
        return 0
    else:
        return key[0] << 8


class JoinAndFTTestCase(unittest.TestCase):
    expected_files = ['peer']

    def start_peer(self, port, handler):


        q = queue.Queue()

        def run_peer():
            p = MockServer(('0.0.0.0', port), handler)
            q.put(p)
            p.serve_forever()

        peer_thread = threading.Thread(target=run_peer)
        peer_thread.start()
        self.addCleanup(peer_thread.join)

        try:
            peer: MockServer = q.get(timeout=5)
            self.addCleanup(peer.server_close)
            self.addCleanup(peer.shutdown)
        except queue.Empty:
            raise RuntimeError(
                "Could not setup mock peer. This should not happen!") from None

        return peer_thread, peer

    def start_client(self, packet: Packet, port=1400):
        c = MockClient(packet, port=port)

        client_thread = threading.Thread(target=c.run)
        client_thread.start()
        self.addCleanup(c.stop)

        connected = c.clientConnected.wait(3.0)
        if not connected:
            raise AssertionError(f"Could not connect to peer on port {port}")

        return c

    def start_student_peer(self, port: int, node_id, anchor_ip=None, anchor_port=None):

        peer_path = which('peer')
        ip = "127.0.0.1"

        if anchor_port is not None and anchor_ip is not None:
            handler = exec_async(
                [f'{peer_path}', f'{ip}', f'{port}', f'{node_id}',
                 f'{anchor_ip}', f'{anchor_port}'])
        elif node_id is not None:
            handler = exec_async(
                [f'{peer_path}', f'{ip}', f'{port}', f'{node_id}'])
        else:
            handler = exec_async(
                [f'{peer_path}', f'{ip}', f'{port}'])

        return handler

    def setup_student_ring(self, node_ids, port_base=4000, ignore_first_id=False):
        handlers = []
        ports = []
        ip = "127.0.0.1"
        for i, node_id in enumerate(node_ids):
            ports.append(port_base + i)
            if i == 0 and not ignore_first_id:
                handlers.append(self.start_student_peer(port_base, node_id))
            elif i == 0 and ignore_first_id:
                handlers.append(self.start_student_peer(port_base, None))
            else:
                handlers.append(self.start_student_peer(
                    port_base + i, node_id, ip, port_base))

        return handlers, ports

    def test_trigger_join_minimal(self):
        node_id = 42
        anchor_thread, anchor = self.start_peer(1400, ControlPktHandler)
        handler = self.start_student_peer(
            1400, node_id, "127.0.0.1", 1400)

        join_pkt: ControlPacket = anchor.await_packet(ControlPacket, 2.0)
        if join_pkt is None:
            status, out, err = handler.collect()
            self.fail(
                f"Did not receive a JOIN msg within timeout!")

    # def test_join_correct(self):
    #     node_id = 42
    #     node_port = 2000
    #     anchor_thread, anchor = self.start_peer(1400, ControlPktHandler)
    #     handler = self.start_student_peer(
    #         node_port, node_id, "127.0.0.1", 1400)

    #     join_pkt: ControlPacket = anchor.await_packet(ControlPacket, 2.0)
    #     if join_pkt is None:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Did not receive a JOIN msg within timeout! Stdout: {out}, Stderr:{err}")

    #     self.assertEqual(join_pkt.method, 'JOIN')
    #     self.assertEqual(join_pkt.node_id, node_id,
    #                      msg="Peer sent wrong node id in JOIN msg.")
    #     self.assertEqual(join_pkt.ip, ipaddress.IPv4Address("127.0.0.1"),
    #                      msg=f"Peer sent wrong ip in JOIN msg. Raw packet: {join_pkt.raw}")
    #     self.assertEqual(join_pkt.port, node_port,
    #                      msg="Peer sent wrong port in JOIN msg.")

    # def test_full_join_student(self):
    #     node_id = 42
    #     node_port = 2000

    #     succ_id = 100
    #     succ_ip = ipaddress.IPv4Address("127.0.0.1")
    #     succ_port = 1400

    #     pre_id = 10
    #     pre_ip = ipaddress.IPv4Address("127.0.0.1")
    #     pre_port = 1401

    #     anchor_thread, anchor = self.start_peer(1400, GeneralPktHandler)
    #     anchor.send_response = True
    #     notify = ControlPacket('NOTIFY', 0, succ_id, succ_ip, succ_port)
    #     anchor.resp_q.put((notify, "127.0.0.1", node_port))

    #     handler = self.start_student_peer(
    #         node_port, node_id, "127.0.0.1", 1400)

    #     join_pkt: ControlPacket = anchor.await_packet(ControlPacket, 2.0)
    #     if join_pkt is None:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Did not receive a JOIN msg within timeout! Stdout: {out}, Stderr:{err}")

    #     stabilize = ControlPacket('STABILIZE', 0, pre_id, pre_ip, pre_port)
    #     pre = self.start_client(stabilize, port=node_port)

    #     try:
    #         notify2 = pre.await_packet(2.5)
    #         if notify2 is None:
    #             status, out, err = handler.collect()
    #             self.fail(
    #                 f"Did not receive a NOTIFY response for stabilize msg within timeout! Stdout: {out}, Stderr:{err}")

    #     except AssertionError:
    #         raise AssertionError(
    #             'Peer closed connection after STABILIZE! Either it crashed or it tries to send NOTIFY in a separate connection! In the second case: This is stupid but might still be valid.')

    #     self.assertEqual(notify2.method, 'NOTIFY')

    #     stabilize2 = anchor.await_packet(ControlPacket, 5.0)
    #     if stabilize2 is None:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Did not receive a STABILIZE within timeout after JOIN! Stdout: {out}, Stderr:{err}")

    #     self.assertEqual(stabilize2.method, "STABILIZE")

    #     lookup1 = ControlPacket('LOOKUP', pre_id - 5,
    #                             9999, pre_ip, pre_port)  # Should be forwarded
    #     c1 = self.start_client(lookup1, port=node_port)

    #     forwarded_l: ControlPacket = anchor.await_packet(ControlPacket, 2.0)
    #     if not forwarded_l:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Peer did not forward lookup to succ within timeout! JOIN might not be completed. Stdout: {out}, Stderr:{err}")

    #     self.assertEqual(forwarded_l.method, 'LOOKUP',
    #                      msg=f"Expected LOOKUP but got {forwarded_l.method} instead. Is the peer spamming STABILIZE? ")

    #     # Should not be forwarded
    #     lookup2 = ControlPacket('LOOKUP', succ_id - 1,
    #                             9999, succ_ip, succ_port)
    #     c2 = self.start_client(lookup2, port=node_port)

    #     reply: ControlPacket = anchor.await_packet(ControlPacket, 2.0)
    #     if not reply:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Peer did not reply to lookup within timeout! JOIN might not be completed. Stdout: {out}, Stderr:{err}")

    #     self.assertEqual(reply.method, 'REPLY')
    #     self.assertEqual(reply.node_id, succ_id)

    # def test_initial_ring(self):
    #     node_id = 42
    #     node_port = 2000
    #     handler = self.start_student_peer(node_port, node_id)

    #     other_id = 123
    #     other_ip = ipaddress.IPv4Address("127.0.0.1")
    #     other_port = 1400
    #     _, other_peer = self.start_peer(other_port, GeneralPktHandler)

    #     join = ControlPacket('JOIN', 0, other_id, other_ip, other_port)
    #     c1 = self.start_client(join, port=node_port)

    #     notify: ControlPacket = other_peer.await_packet(ControlPacket, 2.0)
    #     if not notify:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Peer did not reply to JOIN within timeout! Expected NOTIFY. Stdout: {out}, Stderr:{err}")

    #     self.assertEqual(notify.method, 'NOTIFY')
    #     self.assertEqual(notify.node_id, node_id)
    #     self.assertEqual(notify.ip, ipaddress.IPv4Address(
    #         "127.0.0.1"))
    #     self.assertEqual(notify.port, node_port)

    #     stabilize: ControlPacket = other_peer.await_packet(ControlPacket, 2.5)
    #     if not stabilize:
    #         status, out, err = handler.collect()
    #         self.fail(
    #             f"Peer did not send STABILIZE within timeout! Stdout: {out}, Stderr:{err}")

    #     self.assertEqual(stabilize.method, 'STABILIZE')
    #     self.assertEqual(stabilize.node_id, node_id)

    # def test_join_mock_peer(self):
    #     log = logging.getLogger(__name__)
    #     node1_id = 100
    #     node1_port = 2000
    #     node1_ip = ipaddress.IPv4Address("127.0.0.1")

    #     node2_id = 200
    #     node2_port = 2001
    #     node2_ip = ipaddress.IPv4Address("127.0.0.1")

    #     mock_id = 150
    #     mock_port = 1400
    #     mock_ip = ipaddress.IPv4Address("127.0.0.1")

    #     handler1 = self.start_student_peer(node1_port, node1_id)
    #     handler2 = self.start_student_peer(
    #         node2_port, node2_id, node1_ip, node1_port)

    #     _, mock = self.start_peer(mock_port, GeneralPktHandler)
    #     mock.send_response = True
    #     mock.resp_q.put(NullPacket())  # Do not respond to notify

    #     join = ControlPacket('JOIN', 0, mock_id, mock_ip, mock_port)
    #     c1 = self.start_client(join, port=node1_port)

    #     notify: ControlPacket = mock.await_packet(ControlPacket, 2.5)
    #     if not notify:
    #         _, out1, err1 = handler1.collect()
    #         _, out2, err2 = handler2.collect()
    #         self.fail(
    #             f"Peer did not reply to JOIN within timeout! Expected NOTIFY. Stdout1: {out1}, Stderr1:{err1}, Stdout2: {out2}, Stderr2:{err2}")

    #     self.assertEqual(notify.method, 'NOTIFY')
    #     self.assertEqual(notify.node_id, node2_id)

    #     stabilize: ControlPacket = mock.await_packet(ControlPacket, 5.0)
    #     if not stabilize:
    #         _, out1, err1 = handler1.collect()
    #         _, out2, err2 = handler2.collect()
    #         self.fail(
    #             f"Peer did not send STABILIZE within timeout! Stdout1: {out1}, Stderr1:{err1}, Stdout2: {out2}, Stderr2:{err2}")

    #     mock.resp_q.put(ControlPacket(
    #         'NOTIFY', 0, stabilize.node_id, stabilize.ip, stabilize.port))

    #     self.assertEqual(stabilize.method, 'STABILIZE')

    #     i = 0
    #     # We might have JOINed to early (before node2 finished). So try again
    #     while stabilize.node_id != node1_id and i < 3:
    #         log.debug("Trying again")
    #         stabilize: ControlPacket = mock.await_packet(ControlPacket, 5.0)
    #         if not stabilize:
    #             _, out1, err1 = handler1.collect()
    #             _, out2, err2 = handler2.collect()
    #             self.fail(
    #                 f"Peer did not send STABILIZE within timeout! Stdout1: {out1}, Stderr1:{err1}, Stdout2: {out2}, Stderr2:{err2}")

    #         self.assertEqual(stabilize.method, 'STABILIZE')
    #         mock.resp_q.put(ControlPacket(
    #             'NOTIFY', 0, stabilize.node_id, stabilize.ip, stabilize.port))
    #         i += 1

    #     self.assertEqual(stabilize.node_id, node1_id)

    # def test_student_code_only_set_get(self):
    #     nodes = [512, 1024, 2048, 4096]
    #     handlers, ports = self.setup_student_ring(nodes)
    #     time.sleep(len(nodes) * 2 + 0.5)

    #     value = b'You have invited all my friends!'
    #     key = b'Good Thinking!'
    #     c1 = self.start_client(DataPacket(
    #         'SET', key=key, value=value), port=ports[0])

    #     try:
    #         c1.await_packet(2.0)
    #     except AssertionError:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive ACK packet. Trace: {trace}')

    #     c2 = self.start_client(DataPacket('GET', key=key), ports[3])
    #     get = c2.await_packet(2.0)
    #     if not get:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive response for GET request! {trace}')

    #     self.assertEqual(get.value, value)

    # def test_FT_minimal(self):
    #     nodes = [512, 1024, 2048, 4096]
    #     handlers, ports = self.setup_student_ring(nodes)
    #     time.sleep(len(nodes) * 2 + 0.5)

    #     key = b"Where's the money, Donny!!"
    #     value = b'Oh! Hi, Marc!'
    #     c1 = self.start_client(DataPacket(
    #         'SET', key=key, value=value), port=ports[0])

    #     try:
    #         c1.await_packet(2.0)
    #     except AssertionError:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive ACK packet. Trace: {trace}')

    #     c2 = self.start_client(ControlPacket(
    #         'FINGER', 0, 0, ipaddress.IPv4Address('0.0.0.0'), 0), port=ports[0])

    #     try:
    #         c2.await_packet(2.0)
    #     except AssertionError:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive ACK packet. Trace: {trace}')

    #     c3 = self.start_client(DataPacket('GET', key=key), ports[0])
    #     get = c3.await_packet(2.0)
    #     if not get:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive response for GET request! {trace}')

    #     self.assertEqual(get.value, value)

    # def test_FT_no_ack(self):
    #     nodes = [512, 1024, 2048, 4096]
    #     handlers, ports = self.setup_student_ring(nodes)
    #     time.sleep(len(nodes) * 2 + 0.5)

    #     key = b"Where's the money, Donny!!"
    #     value = b'Oh! Hi, Marc!'
    #     c1 = self.start_client(DataPacket(
    #         'SET', key=key, value=value), port=ports[0])

    #     try:
    #         c1.await_packet(2.0)
    #     except AssertionError:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive ACK packet. Trace: {trace}')

    #     c2 = self.start_client(ControlPacket(
    #         'FINGER', 0, 0, ipaddress.IPv4Address('0.0.0.0'), 0), port=ports[0])

    #     time.sleep(0.5)

    #     c3 = self.start_client(DataPacket('GET', key=key), ports[0])
    #     get = c3.await_packet(2.0)
    #     if not get:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive response for GET request! {trace}')

    #     self.assertEqual(get.value, value)

    # def test_student_code_only_sg_no_id(self):
    #     nodes = [0, 1024, 2048, 4096]
    #     handlers, ports = self.setup_student_ring(nodes, ignore_first_id=True)
    #     time.sleep(len(nodes) * 2 + 0.5)

    #     value = b'You have invited all my friends!'
    #     key = b'Good Thinking!'
    #     c1 = self.start_client(DataPacket(
    #         'SET', key=key, value=value), port=ports[0])

    #     try:
    #         c1.await_packet(2.0)
    #     except AssertionError:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive ACK packet. Trace: {trace}')

    #     c2 = self.start_client(DataPacket('GET', key=key), ports[3])
    #     get = c2.await_packet(2.0)
    #     if not get:
    #         trace = collect_trace(handlers)
    #         self.fail(f'Did not receive response for GET request! {trace}')

    #     self.assertEqual(get.value, value)


class TextTestResultWithSuccesses(unittest.TextTestResult):
    def __init__(self, stream: typing.TextIO, descriptions: bool, vebosity: int):
        super(TextTestResultWithSuccesses, self).__init__(
            stream, descriptions, vebosity)
        self.successes = []

    def addSuccess(self, test):
        super(TextTestResultWithSuccesses, self).addSuccess(test)
        self.successes.append(test)

import os
def which(name):
    cwd = os.getcwd()
    return f"{cwd}/build/{name}"

def main():
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger(__name__)

    testobj = JoinAndFTTestCase()

    group = "testgroup"
    result_dir = os.getcwd()
    log.info(f"result_dir: {result_dir}")

    with open(os.path.join(result_dir, 'test.log'), 'w') as f:
        runner = unittest.TextTestRunner(stream=f)
        suite = unittest.defaultTestLoader.loadTestsFromModule(testobj)

        res: TextTestResultWithSuccesses = runner.run(suite)

        fails = res.failures
        fails.extend(res.errors)

        if res.wasSuccessful() and len(res.skipped) == 0:
            log.info(f'{group} passed all tests 😊')
        elif res.wasSuccessful():
            log.info(f'{group} passed all tests, but we skipped some! 😊')


if __name__ == '__main__':
    main()
