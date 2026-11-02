"""Loopback-only browser service; inference runs on backend, never in browser."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit,parse_qs
import logging

from brain_v3.providers import strict_json
from .service import EvaluationService,BusyError
from .storage import Store

STATIC=Path(__file__).with_name('static')
DEFAULT_DB=Path(__file__).resolve().parents[1]/'runtime/evaluation_lab/evaluations.sqlite3'


class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,service,port=8891):
        self.service=service;self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port),Handler)
        self.hosts={f'127.0.0.1:{self.server_port}',f'localhost:{self.server_port}'}


class Handler(BaseHTTPRequestHandler):
    server_version='InspectionEvaluationLab/0.1'
    def log_message(self,*args):pass # No model/user payloads or credentials in access logs.
    def setup(self):
        super().setup();self.connection.settimeout(75)

    def respond(self,status,value,mime='application/json; charset=utf-8',filename=None):
        body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Referrer-Policy','no-referrer')
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass

    def local(self):
        if self.headers.get('Host') not in self.server.hosts:
            self.respond(403,{'error':'仅允许本地Host'});return False
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://'+h for h in self.server.hosts}:
            self.respond(403,{'error':'跨来源请求被拒绝'});return False
        if self.headers.get('Sec-Fetch-Site')=='cross-site':
            self.respond(403,{'error':'跨站请求被拒绝'});return False
        return True

    def dispatch_error(self,exc):
        if isinstance(exc,BusyError):self.respond(409,{'error':str(exc)})
        elif isinstance(exc,KeyError):self.respond(404,{'error':'记录不存在'})
        elif isinstance(exc,(ValueError,UnicodeError)):self.respond(400,{'error':str(exc)})
        else:
            logging.getLogger(__name__).error('evaluation API failed: %s',type(exc).__name__)
            self.respond(500,{'error':'本地存储或服务异常；请求未被当作成功。请检查服务终端和存储空间。'})

    def do_GET(self):
        if not self.local():return
        try:
            parsed=urlsplit(self.path);path=parsed.path;query=parse_qs(parsed.query)
            static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            service=self.server.service
            filters={k:query[k][0] for k in ('source','category') if k in query}
            if path in static:
                file,mime=static[path];self.respond(200,(STATIC/file).read_bytes(),mime)
            elif path=='/api/config':self.respond(200,{**service.configuration(),'csrf_token':self.server.token})
            elif path=='/api/dataset':self.respond(200,{'cases':service.cases})
            elif path=='/api/records':self.respond(200,{'records':service.store.records(**filters)})
            elif path.startswith('/api/records/'):self.respond(200,service.store.get(path.rsplit('/',1)[1]))
            elif path=='/api/statistics':self.respond(200,service.statistics(**filters))
            elif path.startswith('/api/batches/'):self.respond(200,service.store.batch(path.rsplit('/',1)[1]))
            elif path=='/api/export':
                kind=query.get('format',['json'])[0];body,mime=service.export(kind,**filters)
                self.respond(200,body,mime,'evaluation-lab.'+{'json':'json','csv':'csv','markdown':'md'}.get(kind,'txt'))
            else:self.respond(404,{'error':'接口不存在；无任务执行或机器人接口'})
        except Exception as exc:self.dispatch_error(exc)

    def do_POST(self):
        if not self.local():return
        if not secrets.compare_digest(self.headers.get('X-Evaluation-Token',''),self.server.token):
            self.respond(403,{'error':'本地令牌失效，请刷新页面'});return
        try:
            if self.headers.get_content_type()!='application/json' or self.headers.get('Transfer-Encoding'):
                self.respond(415,{'error':'要求有长度的application/json'});return
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=64*1024:self.respond(413,{'error':'请求体为空或过大'});return
            raw=self.rfile.read(length)
            if len(raw)!=length:raise ValueError('请求体截断')
            data=strict_json(raw)
            if not isinstance(data,dict):raise ValueError('请求必须为JSON对象')
            service=self.server.service;path=urlsplit(self.path).path
            if path=='/api/models/check':
                if data:raise ValueError('模型目录接口不接收URL或凭据')
                self.respond(200,service.check_models())
            elif path=='/api/evaluate':self.respond(200,service.evaluate(data))
            elif path=='/api/batches':self.respond(202,service.start_batch(data))
            elif path.startswith('/api/annotations/'):
                self.respond(200,service.annotate(path.rsplit('/',1)[1],data))
            else:self.respond(404,{'error':'接口不存在；无授权或执行接口'})
        except Exception as exc:self.dispatch_error(exc)


def main(argv=None):
    parser=argparse.ArgumentParser(description='InspectionBrain Evaluation Lab：本地、不可执行')
    parser.add_argument('--port',type=int,default=8891);parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    args=parser.parse_args(argv)
    store=Store(args.db);store.interrupt_batches();service=EvaluationService(store)
    server=Server(service,args.port)
    print(f'Evaluation Lab listening on loopback port {server.server_port}; Ctrl+C to stop.',flush=True)
    print('REAL LLM / MOCK / RULES 单独统计；草案不可执行。',flush=True)
    try:server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        for thread in service.batch_threads:thread.join(timeout=65)
        if not any(t.is_alive() for t in service.batch_threads):store.close()


if __name__=='__main__':main()
