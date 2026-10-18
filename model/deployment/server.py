"""python -m deployment.server --host 127.0.0.1 --port 8088 (from model/)."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'src')]
from deployment.planning import make_plan
from deployment.runtime import OnnxPredictor,load_session,verified_artifacts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8088)
    args = p.parse_args()
    token = os.environ.get('CHRONOFLOW_PLANNER_TOKEN','')
    if args.host not in ('127.0.0.1','::1','localhost') and len(token)<24:
        p.error('a 24+ character CHRONOFLOW_PLANNER_TOKEN is required for non-loopback binding')
    try:
        session = load_session()
        artifacts = verified_artifacts()
    except (ImportError,OSError,ValueError) as exc:
        p.exit(2,f'Model service not started: {exc}. Install deployment/requirements.txt and verify artifacts; no prior-only fallback.\n')
    gate = threading.BoundedSemaphore(1)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass  # Do not log personal request bodies, task titles or credentials.

        def send(self,status,value):
            data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            return not token or hmac.compare_digest(self.headers.get('Authorization',''),f'Bearer {token}')

        def do_GET(self):
            if self.path!='/health':
                return self.send(404,{'error':'not found'})
            if not self.authorized():
                return self.send(401,{'error':'unauthorized'})
            self.send(200,dict(engine='chronoflow-v4',trained=True,modelSha256=artifacts['chronoflow_predictor.onnx']))

        def do_POST(self):
            if self.path!='/plan':
                return self.send(404,{'error':'not found'})
            if not self.authorized():
                return self.send(401,{'error':'unauthorized'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=512*1024:
                    return self.send(413,{'error':'request too large or empty'})
                self.connection.settimeout(15)
                body=json.loads(self.rfile.read(length))
            except (OSError,ValueError):
                return self.send(400,{'error':'invalid JSON request'})
            if not gate.acquire(blocking=False):
                return self.send(429,{'error':'model service busy; retry shortly'})
            try:
                self.send(200,make_plan(body,lambda config:OnnxPredictor(config,session)))
            except (ValueError,KeyError,TypeError) as exc:
                self.send(422,{'error':str(exc)[:200]})
            except Exception:
                self.send(500,{'error':'model planning failed; previous plan was not changed'})
            finally:
                gate.release()
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'ChronoFlow V4 trained model service: http://{args.host}:{args.port}',flush=True)
    server.serve_forever()


if __name__=='__main__':
    main()
