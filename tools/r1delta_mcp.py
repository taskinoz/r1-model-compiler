"""Minimal client for R1Delta's built-in MCP server (launch option -usemcp).

R1Delta serves MCP over Streamable HTTP on http://127.0.0.1:8765/ by default (start the game with
-usemcp +mcp_start_http) with
the tools execute_console_command, execute_squirrel (server/client/ui VM),
get_game_state, get_console_log and search_script_functions. This client speaks
plain JSON-RPC over HTTP with the standard library only.

  python tools/r1delta_mcp.py state
  python tools/r1delta_mcp.py console "map mp_fracture"
  python tools/r1delta_mcp.py squirrel server "printl(GetMapName())"
  python tools/r1delta_mcp.py log
"""
import argparse
import itertools
import json
import sys
import time
import urllib.error
import urllib.request

PROTOCOL = '2025-03-26'


class R1DeltaMCP:
    def __init__(self, port=8765, path='/', timeout=60):
        self.url = 'http://127.0.0.1:%d%s' % (port, path)
        self.timeout = timeout
        self.session = None
        self.ids = itertools.count(1)
        self.protocol = None  # sent only after initialize negotiates it

    def _post(self, payload):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self.protocol:
            headers['MCP-Protocol-Version'] = self.protocol
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        request = urllib.request.Request(self.url, json.dumps(payload).encode(), headers, method='POST')
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            self.session = response.headers.get('Mcp-Session-Id') or self.session
            body = response.read().decode('utf-8', 'replace')
            if 'text/event-stream' in (response.headers.get('Content-Type') or ''):
                data = [line[5:].strip() for line in body.splitlines() if line.startswith('data:')]
                body = data[-1] if data else ''
        return json.loads(body) if body.strip() else None

    def connect(self):
        reply = self._post({'jsonrpc': '2.0', 'id': next(self.ids), 'method': 'initialize',
                            'params': {'protocolVersion': PROTOCOL, 'capabilities': {},
                                       'clientInfo': {'name': 'r1-model-compiler', 'version': '1'}}})
        # later requests carry the version the server chose
        self.protocol = reply['result'].get('protocolVersion', PROTOCOL)
        self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        return reply['result']

    def call(self, tool, **arguments):
        reply = self._post({'jsonrpc': '2.0', 'id': next(self.ids), 'method': 'tools/call',
                            'params': {'name': tool, 'arguments': arguments}})
        if 'error' in reply:
            raise RuntimeError('%s: %s' % (tool, reply['error']))
        result = reply['result']
        text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
        if result.get('isError'):
            raise RuntimeError('%s failed: %s' % (tool, text))
        return text

    def tools(self):
        return self._post({'jsonrpc': '2.0', 'id': next(self.ids), 'method': 'tools/list'})['result']['tools']

    def console(self, command, capture=True):
        return self.call('execute_console_command', command=command, capture_output=capture)

    def squirrel(self, context, script):
        return self.call('execute_squirrel', context=context, script=script)

    def state(self):
        return self.call('get_game_state')

    def log(self):
        return self.call('get_console_log')


def wait_for_server(port=8765, path='/', timeout=300):
    """Connects once the game has started its MCP server."""
    deadline = time.monotonic() + timeout
    while True:
        client = R1DeltaMCP(port, path)
        try:
            client.connect()
            return client
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--path', default='/')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('state')
    sub.add_parser('log')
    sub.add_parser('tools')
    c = sub.add_parser('console')
    c.add_argument('command')
    s = sub.add_parser('squirrel')
    s.add_argument('context', choices=('server', 'client', 'ui'))
    s.add_argument('script')
    a = p.parse_args(argv)
    client = R1DeltaMCP(a.port, a.path)
    client.connect()
    if a.action == 'state':
        print(client.state())
    elif a.action == 'log':
        print(client.log())
    elif a.action == 'tools':
        print(json.dumps([t['name'] for t in client.tools()]))
    elif a.action == 'console':
        print(client.console(a.command))
    else:
        print(client.squirrel(a.context, a.script))
    return 0


if __name__ == '__main__':
    sys.exit(main())
