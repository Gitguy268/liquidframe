import argparse, errno, socket, webbrowser, threading
import uvicorn

def main():
    parser=argparse.ArgumentParser(description='LiquidFrame — your photos, at home')
    parser.add_argument('--port',type=int,default=4320)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:sock.bind(('127.0.0.1',args.port))
        except OSError as e:
            parser.error(f'Port {args.port} is busy. Use --port with another port.' if e.errno==errno.EADDRINUSE else f'Cannot open the local port: {e.strerror}')
    url=f'http://127.0.0.1:{args.port}'
    print(f'LiquidFrame is local at {url}',flush=True)
    if not args.no_browser:threading.Timer(2,lambda:webbrowser.open(url)).start()
    uvicorn.run('openphoto.api:app',host='127.0.0.1',port=args.port,timeout_graceful_shutdown=3)
if __name__=='__main__':main()
