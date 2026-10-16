import argparse
import webbrowser
from pathlib import Path
from .storage import Store
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description='Local patent family response workbench — no LLM required')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'workbench-data')
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    server = make_server(Store(args.data_dir), args.port)
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
