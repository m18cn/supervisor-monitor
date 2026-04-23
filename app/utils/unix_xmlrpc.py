"""Unix Socket XML-RPC 传输（用于连接仅启用 Unix socket 的 Supervisor）"""
import http.client
import socket
import xmlrpc.client


class UnixStreamHTTPConnection(http.client.HTTPConnection):
    """通过 Unix socket 的 HTTP 连接"""
    def __init__(self, socket_path, *args, **kwargs):
        self.socket_path = socket_path
        super().__init__('localhost', *args, **kwargs)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


class UnixStreamTransport(xmlrpc.client.Transport):
    """Unix socket XML-RPC 传输"""
    def __init__(self, socket_path):
        self.socket_path = socket_path
        super().__init__()

    def make_connection(self, host):
        return UnixStreamHTTPConnection(self.socket_path)


def get_unix_socket_proxy(socket_path: str, path: str = '/RPC2') -> xmlrpc.client.ServerProxy:
    """创建通过 Unix socket 连接的 XML-RPC 代理
    
    Supervisor 的 XML-RPC 路径为 /RPC2，需通过 HTTP 请求格式发送。
    """
    transport = UnixStreamTransport(socket_path)
    return xmlrpc.client.ServerProxy(f'http://localhost{path}', transport=transport)
