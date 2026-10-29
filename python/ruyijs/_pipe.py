"""Bounded, overlapped local Windows named-pipe transport."""

import ctypes as C
from ctypes import wintypes as W
import math
import os
import struct
import time
import uuid

MAX_FRAME = 16 * 1024 * 1024

if os.name == "nt":
    K = C.WinDLL("kernel32", use_last_error=True)

    class Overlapped(C.Structure):
        _fields_ = [("Internal", C.c_size_t), ("InternalHigh", C.c_size_t),
                    ("Offset", W.DWORD), ("OffsetHigh", W.DWORD), ("hEvent", W.HANDLE)]

    def _bind(name, args, result):
        fn = getattr(K, name)
        fn.argtypes, fn.restype = args, result
        return fn

    CreatePipe = _bind("CreateNamedPipeW", [W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD,
                                          W.DWORD, W.DWORD, W.DWORD, C.c_void_p], W.HANDLE)
    CreateEvent = _bind("CreateEventW", [C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR], W.HANDLE)
    CloseHandle = _bind("CloseHandle", [W.HANDLE], W.BOOL)
    Connect = _bind("ConnectNamedPipe", [W.HANDLE, C.POINTER(Overlapped)], W.BOOL)
    Read = _bind("ReadFile", [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD),
                              C.POINTER(Overlapped)], W.BOOL)
    Write = _bind("WriteFile", Read.argtypes, W.BOOL)
    Wait = _bind("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
    Result = _bind("GetOverlappedResult", [W.HANDLE, C.POINTER(Overlapped),
                                          C.POINTER(W.DWORD), W.BOOL], W.BOOL)
    Cancel = _bind("CancelIoEx", [W.HANDLE, C.POINTER(Overlapped)], W.BOOL)

    class Pipe:
        def __init__(self):
            self.name = "\\\\.\\pipe\\ruyijs-" + uuid.uuid4().hex
            self.handle = CreatePipe(self.name, 3 | 0x40000000 | 0x00080000,
                                     0x8, 1, 65536, 65536, 0, None)
            if self.handle == C.c_void_p(-1).value:
                self.handle = None
                raise C.WinError(C.get_last_error())

        def _perform(self, operation, deadline, buffer=None):
            event = CreateEvent(None, True, False, None)
            if not event:
                raise C.WinError(C.get_last_error())
            ov, count, pending = Overlapped(hEvent=event), W.DWORD(), False
            try:
                if operation is Connect:
                    ok = operation(self.handle, C.byref(ov))
                else:
                    ok = operation(self.handle, buffer, len(buffer), C.byref(count), C.byref(ov))
                if ok:
                    return count.value
                error = C.get_last_error()
                if operation is Connect and error == 535:
                    return 0
                if error != 997:
                    raise C.WinError(error)
                pending = True
                remaining = max(0, math.ceil((deadline - time.monotonic()) * 1000))
                status = Wait(event, min(remaining, 0xFFFFFFFE))
                if status == 258:
                    raise TimeoutError("ruyijs named-pipe operation timed out")
                if status != 0:
                    raise C.WinError(C.get_last_error())
                ok = Result(self.handle, C.byref(ov), C.byref(count), False)
                pending = False
                if not ok:
                    raise C.WinError(C.get_last_error())
                return count.value
            finally:
                if pending:
                    Cancel(self.handle, C.byref(ov))
                    Result(self.handle, C.byref(ov), C.byref(count), True)
                CloseHandle(event)

        def connect(self, deadline):
            self._perform(Connect, deadline)

        def _read_exact(self, size, deadline):
            chunks = []
            while size:
                if time.monotonic() >= deadline:
                    raise TimeoutError("ruyijs read timed out")
                buffer = C.create_string_buffer(min(size, 65536))
                count = self._perform(Read, deadline, buffer)
                if not count:
                    raise EOFError("ruyijs pipe closed during a frame")
                chunks.append(buffer.raw[:count])
                size -= count
            return b"".join(chunks)

        def receive(self, deadline):
            size = struct.unpack("<I", self._read_exact(4, deadline))[0]
            if size == 0 or size > MAX_FRAME:
                raise ValueError("invalid ruyijs response frame length")
            return self._read_exact(size, deadline)

        def send(self, data, deadline):
            if not data or len(data) > MAX_FRAME:
                raise ValueError("ruyijs request exceeds frame bounds")
            data = struct.pack("<I", len(data)) + data
            offset = 0
            while offset < len(data):
                if time.monotonic() >= deadline:
                    raise TimeoutError("ruyijs write timed out")
                part = data[offset:offset + 65536]
                count = self._perform(Write, deadline, C.create_string_buffer(part, len(part)))
                if not count:
                    raise EOFError("ruyijs pipe closed during a write")
                offset += count

        def close(self):
            if self.handle is not None:
                CloseHandle(self.handle)
                self.handle = None

else:
    import socket

    class Pipe:
        def __init__(self):
            self.uuid = uuid.uuid4().hex
            self.name = f"/tmp/ruyijs-{self.uuid}.sock"
            if os.path.exists(self.name):
                try:
                    os.unlink(self.name)
                except OSError:
                    pass
            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server.bind(self.name)
            self._server.listen(1)
            self.handle = None

        def connect(self, deadline):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("ruyijs pipe connection timed out")
            self._server.settimeout(remaining)
            try:
                conn, _ = self._server.accept()
                self.handle = conn
                self._server.close()
                self._server = None
            except socket.timeout:
                raise TimeoutError("ruyijs pipe connection timed out")

        def _read_exact(self, size, deadline):
            chunks = []
            received = 0
            while received < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("ruyijs read timed out")
                self.handle.settimeout(remaining)
                try:
                    chunk = self.handle.recv(min(size - received, 65536))
                except socket.timeout:
                    raise TimeoutError("ruyijs read timed out")
                if not chunk:
                    raise EOFError("ruyijs pipe closed during a frame")
                chunks.append(chunk)
                received += len(chunk)
            return b"".join(chunks)

        def receive(self, deadline):
            head = self._read_exact(4, deadline)
            size = struct.unpack("<I", head)[0]
            if size == 0 or size > MAX_FRAME:
                raise ValueError("invalid ruyijs response frame length")
            return self._read_exact(size, deadline)

        def send(self, data, deadline):
            if not data or len(data) > MAX_FRAME:
                raise ValueError("ruyijs request exceeds frame bounds")
            packet = struct.pack("<I", len(data)) + data
            total = len(packet)
            offset = 0
            while offset < total:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("ruyijs write timed out")
                self.handle.settimeout(remaining)
                try:
                    sent = self.handle.send(packet[offset:offset + 65536])
                except socket.timeout:
                    raise TimeoutError("ruyijs write timed out")
                if not sent:
                    raise EOFError("ruyijs pipe closed during a write")
                offset += sent

        def close(self):
            if self.handle is not None:
                try:
                    self.handle.close()
                except OSError:
                    pass
                self.handle = None
            if self._server is not None:
                try:
                    self._server.close()
                except OSError:
                    pass
                self._server = None
            if os.path.exists(self.name):
                try:
                    os.unlink(self.name)
                except OSError:
                    pass
