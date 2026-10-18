import argparse
import errno
import http.client
import json
import webbrowser
from pathlib import Path
from .storage import Store
from .server import instance_info, make_server


def _same_instance(port, data_dir):
    # Direct loopback only: no proxies, redirects, or case-data retrieval.
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', '/api/health')
        response = connection.getresponse()
        body = response.read(4097)
        if response.status != 200 or len(body) > 4096:
            return False
        info = json.loads(body)
        expected = instance_info(data_dir)
        return isinstance(info, dict) and all(info.get(key) == expected[key] for key in ('service', 'data_root'))
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description='Local patent family response workbench — no LLM required')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'workbench-data')
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    try:
        server = make_server(Store(args.data_dir), args.port)
    except OSError as exc:
        occupied = exc.errno == errno.EADDRINUSE or getattr(exc, 'winerror', None) == 10048
        if occupied and _same_instance(args.port, args.data_dir):
            url = f'http://127.0.0.1:{args.port}'
            print(f'工作台已在运行：{url}；继续使用已有案件。', flush=True)
            if args.open:
                webbrowser.open(url)
            return
        if occupied:
            parser.exit(1, f'端口 {args.port} 已被占用，且未确认是同一案件目录的工作台。\n'
                           '请使用 --port 指定另一个端口，例如 --port 8766；现有进程和案件未改动。\n')
        parser.exit(1, f'工作台启动失败：{exc}\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Patent workbench: {url}\nCase data: {args.data_dir.resolve()}\nPress Ctrl+C to stop.', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
